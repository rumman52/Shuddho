import { tool } from "@openrouter/sdk/lib/tool.js";
import { z } from "zod";

export const timeTool = tool({
  name: "get_current_time",
  description: "Get the current date and time in a requested timezone.",
  inputSchema: z.object({
    timezone: z.string().optional().describe("IANA timezone such as UTC or Asia/Dhaka."),
  }),
  execute: async ({ timezone }) => {
    const resolvedTimezone = timezone?.trim() || "UTC";
    return {
      timezone: resolvedTimezone,
      time: new Intl.DateTimeFormat("en-US", {
        dateStyle: "full",
        timeStyle: "long",
        timeZone: resolvedTimezone,
      }).format(new Date()),
    };
  },
});

export const calculatorTool = tool({
  name: "calculate_expression",
  description: "Evaluate a basic arithmetic expression containing numbers and + - * / ( ).",
  inputSchema: z.object({
    expression: z.string().describe("Expression such as 2 * (4 + 3)"),
  }),
  execute: async ({ expression }) => {
    const sanitized = expression.replace(/[^0-9+\-*/().\s]/g, "");
    if (!sanitized.trim()) {
      return {
        expression,
        error: "Expression was empty after sanitization.",
      };
    }

    const result = Function(`"use strict"; return (${sanitized});`)() as number;
    return {
      expression,
      sanitized,
      result,
    };
  },
});

export const defaultTools = [timeTool, calculatorTool] as const;
