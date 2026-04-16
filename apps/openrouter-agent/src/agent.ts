import { OpenRouter } from "@openrouter/sdk";
import { stepCountIs } from "@openrouter/sdk/lib/stop-conditions.js";
import type { StreamableOutputItem } from "@openrouter/sdk/lib/stream-transformers.js";
import type { Tool } from "@openrouter/sdk/lib/tool-types.js";

export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface AgentEvents {
  "message:user": (message: Message) => void;
  "message:assistant": (message: Message) => void;
  "item:update": (item: StreamableOutputItem) => void;
  "stream:start": () => void;
  "stream:delta": (delta: string, accumulated: string) => void;
  "stream:end": (fullText: string) => void;
  "tool:call": (name: string, args: unknown) => void;
  "tool:result": (nameOrCallId: string, result: unknown) => void;
  "reasoning:update": (text: string) => void;
  "thinking:start": () => void;
  "thinking:end": () => void;
  error: (error: Error) => void;
}

export interface AgentConfig {
  apiKey: string;
  model?: string;
  instructions?: string;
  tools?: Tool[];
  maxSteps?: number;
  httpReferer?: string;
  appTitle?: string;
  timeoutMs?: number;
}

interface ResolvedAgentConfig {
  apiKey: string;
  model: string;
  instructions: string;
  tools: Tool[];
  maxSteps: number;
  httpReferer?: string;
  appTitle?: string;
  timeoutMs?: number;
}

type ListenerMap<TEvents extends object> = {
  [TName in keyof TEvents]?: Set<TEvents[TName]>;
};

class TypedEmitter<TEvents extends object> {
  private readonly listeners: ListenerMap<TEvents> = {};

  on<TName extends keyof TEvents>(event: TName, listener: TEvents[TName] & ((...args: never[]) => void)): void {
    const existing = this.listeners[event] ?? new Set<TEvents[TName]>();
    existing.add(listener);
    this.listeners[event] = existing;
  }

  off<TName extends keyof TEvents>(event: TName, listener: TEvents[TName] & ((...args: never[]) => void)): void {
    this.listeners[event]?.delete(listener);
  }

  emit<TName extends keyof TEvents>(
    event: TName,
    ...args: TEvents[TName] extends (...params: infer TParams) => void ? TParams : never
  ): void {
    for (const listener of this.listeners[event] ?? []) {
      (listener as (...params: typeof args) => void)(...args);
    }
  }
}

export class Agent {
  private readonly client: OpenRouter;
  private readonly config: ResolvedAgentConfig;
  private readonly messages: Message[] = [];
  private readonly emitter = new TypedEmitter<AgentEvents>();

  constructor(config: AgentConfig) {
    this.config = {
      apiKey: config.apiKey,
      model: config.model ?? "openrouter/auto",
      instructions: config.instructions ?? "You are a helpful assistant.",
      tools: [...(config.tools ?? [])],
      maxSteps: config.maxSteps ?? 5,
      httpReferer: config.httpReferer,
      appTitle: config.appTitle,
      timeoutMs: config.timeoutMs,
    };
    this.client = new OpenRouter({
      apiKey: this.config.apiKey,
      httpReferer: this.config.httpReferer,
      appTitle: this.config.appTitle,
      timeoutMs: this.config.timeoutMs,
    });
  }

  get model(): string {
    return this.config.model;
  }

  on<TName extends keyof AgentEvents>(event: TName, listener: AgentEvents[TName]): void {
    this.emitter.on(event, listener);
  }

  off<TName extends keyof AgentEvents>(event: TName, listener: AgentEvents[TName]): void {
    this.emitter.off(event, listener);
  }

  getMessages(): Message[] {
    return [...this.messages];
  }

  clearHistory(): void {
    this.messages.length = 0;
  }

  setInstructions(instructions: string): void {
    this.config.instructions = instructions;
  }

  addTool(newTool: Tool): void {
    this.config.tools.push(newTool);
  }

  async send(content: string): Promise<string> {
    const userMessage: Message = { role: "user", content };
    this.messages.push(userMessage);
    this.emitter.emit("message:user", userMessage);
    this.emitter.emit("thinking:start");

    try {
      const result = this.client.callModel({
        model: this.config.model,
        instructions: this.config.instructions,
        input: this.messages.map((message) => ({
          role: message.role,
          content: message.content,
        })),
        tools: this.config.tools.length ? this.config.tools : undefined,
        stopWhen: [stepCountIs(this.config.maxSteps)],
      });

      this.emitter.emit("stream:start");
      let fullText = "";

      for await (const item of result.getItemsStream()) {
        this.emitter.emit("item:update", item);

        if (item.type === "message") {
          const nextText = extractOutputText(item);
          if (nextText !== fullText) {
            const delta = nextText.slice(fullText.length);
            fullText = nextText;
            if (delta) {
              this.emitter.emit("stream:delta", delta, fullText);
            }
          }
          continue;
        }

        if (item.type === "function_call" && item.status === "completed") {
          this.emitter.emit("tool:call", item.name, parseJsonSafely(item.arguments));
          continue;
        }

        if (item.type === "function_call_output") {
          this.emitter.emit("tool:result", item.callId, item.output);
          continue;
        }

        if (item.type === "reasoning") {
          const reasoningText = extractReasoningText(item);
          if (reasoningText) {
            this.emitter.emit("reasoning:update", reasoningText);
          }
        }
      }

      if (!fullText) {
        fullText = await result.getText();
      }

      this.emitter.emit("stream:end", fullText);
      const assistantMessage: Message = { role: "assistant", content: fullText };
      this.messages.push(assistantMessage);
      this.emitter.emit("message:assistant", assistantMessage);
      return fullText;
    } catch (error) {
      const resolvedError = error instanceof Error ? error : new Error(String(error));
      this.emitter.emit("error", resolvedError);
      throw resolvedError;
    } finally {
      this.emitter.emit("thinking:end");
    }
  }

  async sendSync(content: string): Promise<string> {
    const userMessage: Message = { role: "user", content };
    this.messages.push(userMessage);
    this.emitter.emit("message:user", userMessage);

    try {
      const result = this.client.callModel({
        model: this.config.model,
        instructions: this.config.instructions,
        input: this.messages.map((message) => ({
          role: message.role,
          content: message.content,
        })),
        tools: this.config.tools.length ? this.config.tools : undefined,
        stopWhen: [stepCountIs(this.config.maxSteps)],
      });
      const fullText = await result.getText();
      const assistantMessage: Message = { role: "assistant", content: fullText };
      this.messages.push(assistantMessage);
      this.emitter.emit("message:assistant", assistantMessage);
      return fullText;
    } catch (error) {
      const resolvedError = error instanceof Error ? error : new Error(String(error));
      this.emitter.emit("error", resolvedError);
      throw resolvedError;
    }
  }
}

export function createAgent(config: AgentConfig): Agent {
  return new Agent(config);
}

function extractOutputText(item: Extract<StreamableOutputItem, { type: "message" }>): string {
  const outputTextPart = item.content.find((part) => part.type === "output_text");
  if (!outputTextPart || !("text" in outputTextPart)) {
    return "";
  }
  return typeof outputTextPart.text === "string" ? outputTextPart.text : "";
}

function extractReasoningText(item: Extract<StreamableOutputItem, { type: "reasoning" }>): string {
  const parts = item.content ?? [];
  const reasoningPart = parts.find((part) => part.type === "reasoning_text");
  if (!reasoningPart || !("text" in reasoningPart)) {
    return "";
  }
  return typeof reasoningPart.text === "string" ? reasoningPart.text : "";
}

function parseJsonSafely(rawValue: string): unknown {
  try {
    return JSON.parse(rawValue);
  } catch {
    return rawValue;
  }
}
