import React, { useCallback, useEffect, useState } from 'react';
import { Linking, StyleSheet, Text, View } from 'react-native';
import { api, ApiError, Me, TelegramLinkInfo, TelegramState } from '../api/client';
import {
  Badge, Banner, Button, Card, LoadingState, Screen, SectionTitle, StepRow,
} from '../components/ui';
import { brand, colors, spacing, typography } from '../theme/tokens';

/**
 * Account screen, which doubles as the Telegram verification checklist — the
 * step a newly signed-up candidate has to finish before anything else opens.
 */
export function AccountScreen({ onSignedOut }: { onSignedOut: () => void }) {
  const [me, setMe] = useState<Me | null>(null);
  const [state, setState] = useState<TelegramState | null>(null);
  const [link, setLink] = useState<TelegramLinkInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [profile, tg, linkInfo] = await Promise.all([
        api.me(),
        api.telegramState().catch(() => null),
        api.telegramLink().catch(() => null),
      ]);
      setMe(profile);
      setState(tg);
      setLink(linkInfo);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load your account.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const recheck = async () => {
    setBusy(true);
    setError(null);
    try {
      setState(await api.telegramRecheck());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not re-check your Telegram status.');
    } finally {
      setBusy(false);
    }
  };

  const signOut = async () => {
    await api.logout();
    onSignedOut();
  };

  if (!me) return <LoadingState label="Loading your account…" />;

  const verified = state?.complete ?? false;

  return (
    <Screen>
      <SectionTitle hint={brand.legalName}>Your account</SectionTitle>

      {error ? <Banner tone="danger" title="Something went wrong" message={error} /> : null}

      <Card>
        <View style={styles.row}>
          <Text style={styles.rowLabel}>Mobile</Text>
          <Text style={styles.rowValue}>{me.mobile}</Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.rowLabel}>Referral code</Text>
          <Text style={styles.rowValue}>{me.referralCode}</Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.rowLabel}>Status</Text>
          <Badge label={me.status.replace(/_/g, ' ')} tone={verified ? 'success' : 'warning'} />
        </View>
      </Card>

      {!verified ? (
        <>
          <Banner
            tone="warning"
            title="Finish verifying on Telegram"
            message="Your account stays limited until all four steps below are done."
          />

          <Card>
            <StepRow
              done={state?.botStarted ?? false}
              title="Start the bot and send your Aadhaar number"
              description="The bot matches it to your account. It is never shown back to you or to anyone else."
            />
            <StepRow
              done={state?.contactVerified ?? false}
              title="Share your contact"
              description="Telegram confirms the number is yours. It must match the number you signed up with."
            />
            <StepRow
              done={state?.joinedPublicChat ?? false}
              title="Join the public channel"
            />
            <StepRow
              done={state?.joinedPrivateChat ?? false}
              title="Request to join the private channel"
              description="Sending the request is enough — an admin approves it later."
            />
          </Card>

          <Card>
            {link ? (
              <>
                <Button label="Open the BBAZAAR bot" onPress={() => Linking.openURL(link.botLink)} />
                {link.publicChatInviteLink ? (
                  <Button
                    label="Open public channel"
                    variant="ghost"
                    onPress={() => Linking.openURL(link.publicChatInviteLink!)}
                  />
                ) : null}
                {link.privateChatInviteLink ? (
                  <Button
                    label="Open private channel"
                    variant="ghost"
                    onPress={() => Linking.openURL(link.privateChatInviteLink!)}
                  />
                ) : null}
              </>
            ) : null}
            <Button label="I've done these — check again" onPress={recheck} variant="secondary" loading={busy} />
          </Card>
        </>
      ) : (
        <Banner tone="success" title="Your account is verified" message="All Telegram steps are complete." />
      )}

      <Button label="Log out" onPress={signOut} variant="danger" />

      <Text style={styles.privacy}>
        Your Aadhaar number is stored only as a one-way hash, never in readable form, and is never
        shown to other candidates.
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.md },
  rowLabel: { ...typography.body, color: colors.textSecondary },
  rowValue: { ...typography.bodyStrong, color: colors.textPrimary },
  privacy: { ...typography.caption, color: colors.textMuted, textAlign: 'center' },
});
