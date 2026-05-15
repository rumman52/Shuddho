export interface PrivacyContext {
  userId: string;
  tenantId: string;
  allowProductImprovement: boolean;
}

export function applyDlpPlaceholder(text: string): { safeText: string; findings: string[] } {
  const findings: string[] = [];
  const safeText = text.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, () => {
    findings.push('email');
    return '[email]';
  });
  return { safeText, findings };
}

export function canProcessText(_context: PrivacyContext): boolean {
  return true;
}
