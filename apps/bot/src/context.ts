import { Context } from 'telegraf';

export type BankDetailsStep =
  | 'AWAITING_HOLDER_NAME'
  | 'AWAITING_ACCOUNT_NUMBER'
  | 'AWAITING_IFSC'
  | 'AWAITING_UPI_OPTIONAL'
  | null;

export interface SessionData {
  bankDetailsStep: BankDetailsStep;
  bankDetailsDraft: {
    bankAccountHolder?: string;
    bankAccountNumber?: string;
    bankIfsc?: string;
  };
}

export interface BotContext extends Context {
  session: SessionData;
}

export function defaultSession(): SessionData {
  return { bankDetailsStep: null, bankDetailsDraft: {} };
}
