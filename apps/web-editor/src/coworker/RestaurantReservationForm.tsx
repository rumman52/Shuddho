import { useEffect, useState, type FormEvent } from "react";
import { CoworkerClient, type RestaurantReservationSurface } from "./client";

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "This reservation review could not be created.";

export default function RestaurantReservationForm({
  client,
  onCreated,
}: {
  client: CoworkerClient;
  onCreated: (surface: RestaurantReservationSurface) => void;
}) {
  const [available, setAvailable] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [restaurantId, setRestaurantId] = useState("");
  const [restaurantName, setRestaurantName] = useState("");
  const [dateTime, setDateTime] = useState("");
  const [timeZone, setTimeZone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const [partySize, setPartySize] = useState("2");
  const [seating, setSeating] = useState<"default" | "hightop" | "bar" | "counter" | "outdoor">("default");
  const [diningAreaId, setDiningAreaId] = useState("");
  const [environment, setEnvironment] = useState<"" | "Indoor" | "Outdoor">("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [country, setCountry] = useState("");
  const [specialRequest, setSpecialRequest] = useState("");
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [contactSharing, setContactSharing] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    client.connections(controller.signal).then(value => {
      if (controller.signal.aborted) return;
      setAvailable(
        value.enabled
        && value.personal_transactions_enabled
        && value.restaurant_reservations_enabled
        && (value.transaction_operations ?? []).includes("opentable:restaurant_reservation_create"),
      );
      setLoaded(true);
    }).catch(failure => {
      if (!controller.signal.aborted) {
        setError(errorMessage(failure));
        setLoaded(true);
      }
    });
    return () => controller.abort();
  }, [client]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!available || busy || !termsAccepted || !contactSharing) return;
    setBusy(true);
    setError("");
    try {
      const rid = Number(restaurantId);
      const party = Number(partySize);
      const area = diningAreaId ? Number(diningAreaId) : null;
      if (!Number.isSafeInteger(rid) || rid < 1) throw new Error("Enter a valid OpenTable restaurant ID.");
      if (!Number.isSafeInteger(party) || party < 1 || party > 20) throw new Error("Party size must be 1–20.");
      if (area !== null && (!Number.isSafeInteger(area) || area < 1)) throw new Error("Dining area ID must be a positive number.");
      if (!dateTime) throw new Error("Choose the exact reservation date and time.");
      const surface = await client.createRestaurantReservation({
        restaurant_id: rid,
        restaurant_name: restaurantName,
        date_time: dateTime,
        time_zone: timeZone,
        party_size: party,
        reservation_attribute: seating,
        dining_area_id: area,
        environment: environment || null,
        guest_first_name: firstName,
        guest_last_name: lastName,
        guest_email: email,
        guest_phone_number: phone,
        guest_phone_country_code: country.toUpperCase(),
        special_request: specialRequest,
        opentable_terms_accepted: true,
        opentable_terms_version: "2026-07-22",
        guest_contact_sharing_approved: true,
      }, crypto.randomUUID());
      onCreated(surface);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  if (!loaded) return <p>Checking restaurant reservation availability…</p>;
  if (!available) return null;

  return <form onSubmit={submit}>
    <h3>New OpenTable reservation review</h3>
    <p className="cw-fineprint">
      Shuddho checks the exact requested slot first. Creating this review does not book a table.
      Only a later separately approved ExternalAction can submit one standard no-payment reservation.
    </p>
    {error && <p className="cw-error" role="alert">{error}</p>}
    <label>OpenTable restaurant ID<input inputMode="numeric" value={restaurantId} required onChange={event => setRestaurantId(event.target.value)} /></label>
    <label>Restaurant name<input value={restaurantName} required maxLength={300} onChange={event => setRestaurantName(event.target.value)} /></label>
    <label>Reservation date and time<input type="datetime-local" step={900} value={dateTime} required onChange={event => setDateTime(event.target.value)} /></label>
    <label>IANA time zone<input value={timeZone} required maxLength={80} onChange={event => setTimeZone(event.target.value)} /></label>
    <label>Party size<input inputMode="numeric" min={1} max={20} value={partySize} required onChange={event => setPartySize(event.target.value)} /></label>
    <label>Seating<select value={seating} onChange={event => setSeating(event.target.value as typeof seating)}>
      <option value="default">Standard / default</option>
      <option value="hightop">High-top</option>
      <option value="bar">Bar</option>
      <option value="counter">Counter</option>
      <option value="outdoor">Outdoor</option>
    </select></label>
    <label>Dining area ID (optional)<input inputMode="numeric" value={diningAreaId} onChange={event => setDiningAreaId(event.target.value)} /></label>
    <label>Environment (optional)<select value={environment} onChange={event => setEnvironment(event.target.value as typeof environment)}>
      <option value="">Any approved environment</option>
      <option value="Indoor">Indoor</option>
      <option value="Outdoor">Outdoor</option>
    </select></label>
    <label>Guest first name<input value={firstName} required maxLength={100} autoComplete="given-name" onChange={event => setFirstName(event.target.value)} /></label>
    <label>Guest last name<input value={lastName} required maxLength={100} autoComplete="family-name" onChange={event => setLastName(event.target.value)} /></label>
    <label>Guest email<input type="email" value={email} required maxLength={254} autoComplete="email" onChange={event => setEmail(event.target.value)} /></label>
    <label>Guest phone<input value={phone} required maxLength={20} autoComplete="tel" placeholder="+14155550123" onChange={event => setPhone(event.target.value)} /></label>
    <label>Phone country code<input value={country} required minLength={2} maxLength={2} placeholder="US" onChange={event => setCountry(event.target.value.toUpperCase())} /></label>
    <label>Special request (optional)<textarea rows={2} maxLength={75} value={specialRequest} onChange={event => setSpecialRequest(event.target.value)} /></label>

    <label className="cw-approval-check">
      <input type="checkbox" checked={termsAccepted} required onChange={event => setTermsAccepted(event.target.checked)} />
      <span>
        I have read and accept the{" "}
        <a href="https://www.opentable.com/c/legal/terms-and-conditions/" target="_blank" rel="noopener noreferrer">
          OpenTable Terms of Use
        </a>{" "}
        for this reservation.
      </span>
    </label>
    <label className="cw-approval-check">
      <input type="checkbox" checked={contactSharing} required onChange={event => setContactSharing(event.target.checked)} />
      I authorize Shuddho to send the guest name, email and phone entered above to OpenTable for this reservation and its confirmation.
    </label>

    <button className="cw-primary" type="submit" disabled={busy || !termsAccepted || !contactSharing}>
      {busy ? "Checking exact availability…" : "Check availability & create review"}
    </button>
    <p className="cw-fineprint">
      TX-06 excludes credit-card, deposit, hold, prepayment and experience inventory. If the provider requires payment, Shuddho will not escalate into a payment flow.
    </p>
  </form>;
}
