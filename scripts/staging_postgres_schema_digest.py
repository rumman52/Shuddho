"""Canonical, read-only structure digest for a private PostgreSQL schema.

A migration revision and matching row hashes do not establish structural
equivalence: changed defaults, indexes, policies or constraints can leave
every stored row unchanged. Hash pg_catalog records from the *same* snapshot
used by the backup inventory and compare them after an isolated restore.

Exclude OIDs, physical file names, object ownership and discretionary ACLs,
which change intentionally when pg_restore uses --no-owner --no-privileges.
The private Supabase API-role grant boundary is audited separately.
"""
from __future__ import annotations

from hashlib import sha256


class SchemaCatalogError(RuntimeError):
    """The private schema catalog could not be completely read."""


# Each query returns one canonical jsonb text record per structural object.
# Do not interpolate the schema name into SQL: every query binds it separately.
CATALOG_QUERIES: tuple[tuple[str, str], ...] = (
    (
        "relations",
        """
        SELECT jsonb_build_object(
            'name', c.relname, 'kind', c.relkind::text,
            'persistence', c.relpersistence::text,
            'row_security', c.relrowsecurity, 'force_row_security', c.relforcerowsecurity,
            'partition_bound', pg_get_expr(c.relpartbound, c.oid),
            'view_definition', CASE WHEN c.relkind IN ('v', 'm')
                THEN pg_get_viewdef(c.oid, false) ELSE NULL END,
            'options', COALESCE(
                (SELECT jsonb_agg(option ORDER BY option)
                 FROM unnest(c.reloptions) AS option), '[]'::jsonb)
        )::text
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
        """,
    ),
    (
        "columns",
        """
        SELECT jsonb_build_object(
            'relation', c.relname, 'ordinal', a.attnum, 'name', a.attname,
            'type', format_type(a.atttypid, a.atttypmod),
            'not_null', a.attnotnull,
            'identity', a.attidentity::text,
            'generated', a.attgenerated::text,
            'default', pg_get_expr(d.adbin, d.adrelid),
            'collation', CASE WHEN a.attcollation = 0 THEN NULL
                ELSE coll.collname END,
            'storage', a.attstorage::text
        )::text
        FROM pg_attribute AS a
        JOIN pg_class AS c ON c.oid = a.attrelid
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        LEFT JOIN pg_attrdef AS d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        LEFT JOIN pg_collation AS coll ON coll.oid = a.attcollation
        WHERE n.nspname = %s AND a.attnum > 0 AND NOT a.attisdropped
          AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
        """,
    ),
    (
        "constraints",
        """
        SELECT jsonb_build_object(
            'table', t.relname, 'name', con.conname, 'kind', con.contype::text,
            'definition', pg_get_constraintdef(con.oid, false),
            'deferrable', con.condeferrable, 'initially_deferred', con.condeferred,
            'validated', con.convalidated
        )::text
        FROM pg_constraint AS con
        JOIN pg_class AS t ON t.oid = con.conrelid
        JOIN pg_namespace AS n ON n.oid = t.relnamespace
        WHERE n.nspname = %s
        """,
    ),
    (
        "indexes",
        """
        SELECT jsonb_build_object(
            'table', t.relname, 'name', idx.relname,
            'definition', pg_get_indexdef(idx.oid),
            'unique', i.indisunique, 'primary', i.indisprimary,
            'valid', i.indisvalid, 'ready', i.indisready
        )::text
        FROM pg_index AS i
        JOIN pg_class AS idx ON idx.oid = i.indexrelid
        JOIN pg_class AS t ON t.oid = i.indrelid
        JOIN pg_namespace AS n ON n.oid = t.relnamespace
        WHERE n.nspname = %s
        """,
    ),
    (
        "triggers",
        """
        SELECT jsonb_build_object(
            'table', c.relname, 'name', t.tgname,
            'definition', pg_get_triggerdef(t.oid, false),
            'enabled', t.tgenabled::text
        )::text
        FROM pg_trigger AS t
        JOIN pg_class AS c ON c.oid = t.tgrelid
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND NOT t.tgisinternal
        """,
    ),
    (
        "policies",
        """
        SELECT jsonb_build_object(
            'table', c.relname, 'name', p.polname,
            'permissive', p.polpermissive, 'command', p.polcmd::text,
            'using', pg_get_expr(p.polqual, p.polrelid),
            'check', pg_get_expr(p.polwithcheck, p.polrelid),
            'public', 0::oid = ANY(p.polroles),
            'roles', COALESCE(
                (SELECT jsonb_agg(r.rolname ORDER BY r.rolname)
                 FROM pg_roles AS r WHERE r.oid = ANY(p.polroles)), '[]'::jsonb)
        )::text
        FROM pg_policy AS p
        JOIN pg_class AS c ON c.oid = p.polrelid
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = %s
        """,
    ),
    (
        "sequences",
        """
        SELECT jsonb_build_object(
            'name', c.relname, 'type', format_type(s.seqtypid, NULL),
            'start', s.seqstart, 'increment', s.seqincrement,
            'minimum', s.seqmin, 'maximum', s.seqmax,
            'cache', s.seqcache, 'cycle', s.seqcycle
        )::text
        FROM pg_sequence AS s
        JOIN pg_class AS c ON c.oid = s.seqrelid
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = %s
        """,
    ),
    (
        "routines",
        """
        SELECT jsonb_build_object(
            'name', p.proname, 'arguments', pg_get_function_identity_arguments(p.oid),
            'kind', p.prokind::text,
            'definition', pg_get_functiondef(p.oid)
        )::text
        FROM pg_proc AS p
        JOIN pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = %s AND p.prokind IN ('f', 'p')
        """,
    ),
    (
        "enum_and_domain_types",
        """
        SELECT jsonb_build_object(
            'name', t.typname, 'kind', t.typtype::text,
            'base_type', CASE WHEN t.typbasetype = 0 THEN NULL
                ELSE format_type(t.typbasetype, t.typtypmod) END,
            'not_null', t.typnotnull, 'default', t.typdefault,
            'enum_labels', COALESCE(
                (SELECT jsonb_agg(e.enumlabel ORDER BY e.enumsortorder)
                 FROM pg_enum AS e WHERE e.enumtypid = t.oid), '[]'::jsonb),
            'constraints', COALESCE(
                (SELECT jsonb_agg(con.conname || ':' || pg_get_constraintdef(con.oid, false)
                                  ORDER BY con.conname)
                 FROM pg_constraint AS con WHERE con.contypid = t.oid), '[]'::jsonb)
        )::text
        FROM pg_type AS t
        JOIN pg_namespace AS n ON n.oid = t.typnamespace
        WHERE n.nspname = %s AND t.typtype IN ('e', 'd', 'r', 'm')
        """,
    ),
)


def catalog_schema_sha256(connection, schema: str) -> str:
    """Hash schema metadata without copying source rows or returning PII.

    Query the source under its existing REPEATABLE READ read-only snapshot;
    call under a separate isolated-target snapshot for exact comparison.
    The only public result is a lowercase hexadecimal SHA-256 digest.
    """
    if not isinstance(schema, str) or not schema or len(schema) > 128:
        raise SchemaCatalogError("A private schema name is required.")
    digest = sha256()
    for category, query in CATALOG_QUERIES:
        try:
            rows = connection.execute(query, (schema,)).fetchall()
            if len(rows) > 50_000:
                raise SchemaCatalogError("Private schema catalog inventory exceeds the allowed limit.")
            descriptions = []
            for row in rows:
                if len(row) != 1 or not isinstance(row[0], str):
                    raise SchemaCatalogError("Private schema catalog returned a malformed record.")
                descriptions.append(row[0])
        except SchemaCatalogError:
            raise
        except Exception:
            raise SchemaCatalogError("Private schema catalog could not be read.") from None
        digest.update((category + "\n").encode("utf-8"))
        for description in sorted(descriptions):
            digest.update((description + "\n").encode("utf-8"))
    return digest.hexdigest()
