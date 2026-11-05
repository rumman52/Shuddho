import { ErrorBoundary } from "../../web-editor/src/components/ErrorBoundary";
import CoworkerGate from "../../web-editor/src/coworker/CoworkerGate";


export default function App() {
  return (
    <ErrorBoundary>
      <div className="rukh-coworker-app">
        <CoworkerGate />
      </div>
    </ErrorBoundary>
  );
}
