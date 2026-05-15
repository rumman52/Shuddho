import { createServer } from 'node:http';
import { loadApiEnv } from '@shuddho/config';
import { logger } from '@shuddho/observability';
import { createApp } from './app.js';
import { attachDocumentSync } from './ws/document-sync.js';

const env = loadApiEnv();
const app = createApp();
const server = createServer(app);
attachDocumentSync(server, app.locals.documents);
server.listen(env.PORT, () => logger.info({ port: env.PORT }, 'api listening'));
