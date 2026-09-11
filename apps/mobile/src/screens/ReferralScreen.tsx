import React, { useCallback, useEffect, useState } from 'react';
import * as Clipboard from 'expo-clipboard';
import { StyleSheet, Text, View } from 'react-native';
import { api, ApiError, ReferralSummary } from '../api/client';
import { AdBanner } from '../components/AdBanner';
import {
  Badge, Banner, Button, Card, LoadingState, ProgressBar, Screen, SectionTitle, StatTile,
} from '../components/ui';
import { colors, spacing, typography } from '../theme/tokens';

/**
 * Referral dashboard: the link to share, progress toward the ceiling, and the
 * breakdown of verified / rejected / still pending.
 *
 * Every number shown here is computed server-side. The screen renders them and
 * nothing more, so the counts cannot be inflated by editing the app.
 */
export function ReferralScreen() {
  const [data, setData] = useState<ReferralSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await api.referrals());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load your referrals.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <Screen>
        <Banner tone="danger" title="Could not load referrals" message={error} />
        <Button label="Try again" onPress={load} variant="ghost" />
      </Screen>
    );
  }

  if (!data) return <LoadingState label="Loading your referrals…" />;

  const { stats, referrals, referralCode } = data;
  const shareLink = `https://bbazaar.example/join?ref=${referralCode}`;

  const copy = async () => {
    await Clipboard.setStringAsync(shareLink);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const nearingSuspension = stats.fraud.remainingBeforeSuspension <= 3 && stats.fraud.strikes > 0;

  return (
    <Screen>
      <SectionTitle hint={`Target: ${stats.ceiling} verified referrals`}>Your referrals</SectionTitle>

      <Card>
        <Text style={styles.codeLabel}>YOUR REFERRAL LINK</Text>
        <Text style={styles.codeValue} selectable numberOfLines={2}>
          {shareLink}
        </Text>
        <View style={styles.codeRow}>
          <Badge label={`Code: ${referralCode}`} tone="info" />
          <Button
            label={copied ? 'Copied' : 'Copy link'}
            onPress={copy}
            variant="secondary"
            style={styles.copyButton}
          />
        </View>
      </Card>

      <Card>
        <View style={styles.progressHead}>
          <Text style={styles.progressTitle}>
            {stats.verified} of {stats.ceiling} verified
          </Text>
          <Badge
            label={stats.ceilingReached ? 'Target met' : `${stats.remaining} to go`}
            tone={stats.ceilingReached ? 'success' : 'default'}
          />
        </View>
        <ProgressBar
          current={stats.verified}
          total={stats.ceiling}
          tone={stats.ceilingReached ? 'success' : 'brand'}
        />
        <Text style={styles.progressCaption}>
          A referral counts only after that person finishes their own verification.
        </Text>
      </Card>

      <View style={styles.statRow}>
        <StatTile value={stats.total} label="Signed up" />
        <StatTile value={stats.verified} label="KYC approved" tone="success" />
      </View>
      <View style={styles.statRow}>
        <StatTile value={stats.pending} label="Still verifying" tone="warning" />
        <StatTile value={stats.rejected} label="Rejected" tone="danger" />
      </View>

      {stats.ceilingReached ? (
        <Banner
          tone="success"
          title="Referral target complete"
          message="You have reached the referral ceiling. Finish your KYC training to unlock your application."
        />
      ) : null}

      {nearingSuspension ? (
        <Banner
          tone="warning"
          title={`${stats.fraud.strikes} rejected referral${stats.fraud.strikes === 1 ? '' : 's'} on your account`}
          message={`Accounts reaching ${stats.fraud.limit} rejected referrals are suspended. Only invite people you know are using their own genuine details.`}
        />
      ) : null}

      <AdBanner />

      <SectionTitle>Referral history</SectionTitle>
      {referrals.length === 0 ? (
        <Card>
          <Text style={styles.emptyText}>
            No referrals yet. Share your link above to get started.
          </Text>
        </Card>
      ) : (
        referrals.map((r) => (
          <Card key={r.id} style={styles.historyCard}>
            <View style={styles.historyRow}>
              <Text style={styles.historyDate}>
                {new Date(r.createdAt).toLocaleDateString('en-IN', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                })}
              </Text>
              <Badge label={STATUS_LABEL[r.status] ?? r.status} tone={STATUS_TONE[r.status] ?? 'default'} />
            </View>
            {r.rejectionReasonCode ? (
              <Text style={styles.historyReason}>Reason: {r.rejectionReasonCode}</Text>
            ) : null}
          </Card>
        ))
      )}
    </Screen>
  );
}

const STATUS_LABEL: Record<string, string> = {
  PENDING: 'Verifying',
  ELIGIBLE: 'Verifying',
  CREDITED: 'Approved',
  REJECTED: 'Rejected',
};

const STATUS_TONE: Record<string, 'default' | 'success' | 'warning' | 'danger' | 'info'> = {
  PENDING: 'warning',
  ELIGIBLE: 'warning',
  CREDITED: 'success',
  REJECTED: 'danger',
};

const styles = StyleSheet.create({
  codeLabel: { ...typography.label, color: colors.textSecondary },
  codeValue: { ...typography.bodyStrong, color: colors.brandNavy },
  codeRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md },
  copyButton: { flexShrink: 0, paddingHorizontal: spacing.lg, minHeight: 44 },

  progressHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  progressTitle: { ...typography.heading, color: colors.textPrimary },
  progressCaption: { ...typography.caption, color: colors.textSecondary },

  statRow: { flexDirection: 'row', gap: spacing.md },

  historyCard: { paddingVertical: spacing.md, gap: spacing.xs },
  historyRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  historyDate: { ...typography.body, color: colors.textPrimary },
  historyReason: { ...typography.caption, color: colors.danger },

  emptyText: { ...typography.body, color: colors.textSecondary, textAlign: 'center' },
});
