import { useCallback, useState } from 'react';
import { api, ApiError } from '../lib/api.js';
import { haptics, openInvoice } from '../lib/telegram.js';

/**
 * One-tap donation.
 *
 * The entire flow behind a single press: create the invoice, open Telegram's
 * native payment sheet, and let the settlement broadcast update the UI. No
 * confirmation step and no amount picker — the tier the user pressed *is* the
 * decision, and asking them to confirm it only loses donations.
 */
export function useQuickDonate(): {
  donate: (standId: string, amountStars: number) => Promise<void>;
  pendingStandId: string | null;
  error: string | null;
  clearError: () => void;
} {
  const [pendingStandId, setPendingStandId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const donate = useCallback(
    async (standId: string, amountStars: number) => {
      // Guard against double-fire: a second tap while the sheet is opening
      // would create a second invoice for the same intent.
      if (pendingStandId) return;

      setPendingStandId(standId);
      setError(null);
      try {
        const { invoiceLink } = await api.starsInvoice({ standId, amountStars });
        const status = await openInvoice(invoiceLink);

        if (status === 'paid') haptics.notify('success');
        else if (status === 'failed') {
          haptics.notify('error');
          setError('Payment did not go through. Nothing was charged.');
        } else if (status === 'cancelled') haptics.impact('light');
      } catch (caught) {
        haptics.notify('error');
        setError(
          caught instanceof ApiError ? caught.message : 'Could not start the payment.',
        );
      } finally {
        setPendingStandId(null);
      }
    },
    [pendingStandId],
  );

  return { donate, pendingStandId, error, clearError: () => setError(null) };
}
