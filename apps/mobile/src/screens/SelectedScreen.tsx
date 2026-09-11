import React, { useCallback, useEffect, useState } from 'react';
import { Linking, StyleSheet, Text, View } from 'react-native';
import { api, ApiError, ReferralSummary, SelectionStatus } from '../api/client';
import { AdBanner } from '../components/AdBanner';
import {
  Banner, Button, Card, LoadingState, ProgressBar, Screen, SectionTitle,
} from '../components/ui';
import { brand, colors, spacing, typography } from '../theme/tokens';

/**
 * The "you're through" screen for candidates who finished both targets.
 *
 * The group invite link is fetched on demand and never bundled with the app —
 * an APK can be unpacked, so a link shipped inside it would be public. The
 * server issues it only to qualified candidates and records each issue.
 */
export function SelectedScreen({ onGoToReferrals }: { onGoToReferrals: () => void }) {
  const [selection, setSelection] = useState<SelectionStatus | null>(null);
  const [progress, setProgress] = useState<ReferralSummary['progress'] | null>(null);
  const [invite, setInvite] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [sel, summary] = await Promise.all([api.selectionStatus(), api.referrals()]);
      setSelection(sel);
      setProgress(summary.progress);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not check your status.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const unlock = async () => {
    setBusy(true);
    setError(null);
    try {
      const { inviteLink } = await api.groupInvite();
      setInvite(inviteLink);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not fetch the group link.');
    } finally {
      setBusy(false);
    }
  };

  if (!selection) return <LoadingState label="Checking your status…" />;

  if (!selection.qualified) {
    return (
      <Screen>
        <SectionTitle hint="Unlocks when both targets are complete.">
          Selected candidates
        </SectionTitle>

        <Card tone="warning">
          <Text style={styles.lockedTitle}>Not unlocked yet</Text>
          <Text style={styles.lockedBody}>
            Once you complete both targets, this is where you will get the invite to the
            selected-candidates group, where training dates, timings and work details are shared.
          </Text>
        </Card>

        {progress ? (
          <Card>
            <Text style={styles.blockTitle}>Referrals</Text>
            <ProgressBar current={progress.referrals.completed} total={progress.referrals.required} />
            <Text style={styles.blockCaption}>
              {progress.referrals.completed} of {progress.referrals.required}
            </Text>

            <View style={styles.divider} />

            <Text style={styles.blockTitle}>KYC training</Text>
            <ProgressBar
              current={progress.kycChallenges.completed}
              total={progress.kycChallenges.required}
            />
            <Text style={styles.blockCaption}>
              {progress.kycChallenges.completed} of {progress.kycChallenges.required}
            </Text>
          </Card>
        ) : null}

        <Button label="Go to my referrals" onPress={onGoToReferrals} variant="ghost" />
        <AdBanner />
      </Screen>
    );
  }

  return (
    <Screen>
      <SectionTitle hint={brand.legalName}>You have been selected</SectionTitle>

      <Card tone="brand" style={styles.hero}>
        <Text style={styles.heroTitle}>Congratulations</Text>
        <Text style={styles.heroBody}>
          You have completed both targets. Join the selected-candidates group to receive your
          training date, timings and work details.
        </Text>
      </Card>

      {error ? <Banner tone="danger" title="Could not fetch the link" message={error} /> : null}

      <Card>
        {invite ? (
          <>
            <Text style={styles.inviteLabel}>YOUR GROUP INVITE</Text>
            <Text style={styles.inviteLink} selectable>
              {invite}
            </Text>
            <Button label="Open in Telegram" onPress={() => Linking.openURL(invite)} />
            <Text style={styles.inviteNote}>
              This invite is issued to your account. Do not share it — every issue is logged.
            </Text>
          </>
        ) : (
          <>
            <Text style={styles.blockTitle}>Selected-candidates group</Text>
            <Text style={styles.blockCaption}>
              Separate from the two channels you joined during verification. This one is only for
              candidates who have been selected.
            </Text>
            <Button label="Get my group invite" onPress={unlock} loading={busy} />
          </>
        )}
      </Card>

      <Card>
        <Text style={styles.blockTitle}>What happens next</Text>
        {NEXT_STEPS.map((step, i) => (
          <View key={step} style={styles.nextRow}>
            <Text style={styles.nextNumber}>{i + 1}</Text>
            <Text style={styles.nextText}>{step}</Text>
          </View>
        ))}
      </Card>

      <AdBanner />
    </Screen>
  );
}

const NEXT_STEPS = [
  'Join the group using the invite above.',
  'Your training date and timings are announced there.',
  'Attend the training session on the given date.',
  'Work location and joining details follow after training.',
];

const styles = StyleSheet.create({
  hero: { gap: spacing.sm },
  heroTitle: { ...typography.display, color: colors.textOnBrand },
  heroBody: { ...typography.body, color: colors.brandGoldSoft },

  lockedTitle: { ...typography.heading, color: colors.warning },
  lockedBody: { ...typography.body, color: colors.textSecondary },

  blockTitle: { ...typography.bodyStrong, color: colors.textPrimary },
  blockCaption: { ...typography.caption, color: colors.textSecondary },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.sm },

  inviteLabel: { ...typography.label, color: colors.textSecondary },
  inviteLink: { ...typography.bodyStrong, color: colors.brandNavy },
  inviteNote: { ...typography.caption, color: colors.textMuted },

  nextRow: { flexDirection: 'row', gap: spacing.md, alignItems: 'flex-start' },
  nextNumber: { ...typography.caption, fontWeight: '700', color: colors.brandGold, width: 16 },
  nextText: { ...typography.caption, color: colors.textSecondary, flex: 1 },
});
