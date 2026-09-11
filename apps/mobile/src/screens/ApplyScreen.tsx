import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { api, ApiError, ReferralSummary, SelectionStatus } from '../api/client';
import { AdBanner } from '../components/AdBanner';
import {
  Badge, Banner, Button, Card, Field, LoadingState, ProgressBar, Screen, SectionTitle,
} from '../components/ui';
import { colors, radius, spacing, typography } from '../theme/tokens';

// Must match the values the server's CreateApplicationDto accepts.
const STATES = ['Rajasthan', 'Uttar Pradesh', 'Gujarat', 'Madhya Pradesh', 'Maharashtra'];
const TIERS = [
  { value: 'tier1', label: 'Tier 1' },
  { value: 'tier2', label: 'Tier 2' },
  { value: 'tier3', label: 'Tier 3' },
];

/**
 * Job application. The form only submits once the server says the candidate is
 * eligible — and the server checks again at submit time, so a candidate who
 * unlocks this screen by tampering still gets a 403.
 */
export function ApplyScreen({ onGoToReferrals }: { onGoToReferrals: () => void }) {
  const [selection, setSelection] = useState<SelectionStatus | null>(null);
  const [progress, setProgress] = useState<ReferralSummary['progress'] | null>(null);
  const [existing, setExisting] = useState<{ id: string; status: string } | null>(null);
  const [state, setState] = useState(STATES[0]);
  const [tier, setTier] = useState(TIERS[0].value);
  const [district, setDistrict] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [sel, summary] = await Promise.all([api.selectionStatus(), api.referrals()]);
      setSelection(sel);
      setProgress(summary.progress);
      try {
        setExisting(await api.myApplication());
      } catch {
        setExisting(null);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load your application status.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.apply({
        statePreference: state,
        tierPreference: tier,
        districtPreference: district.trim() || undefined,
      });
      setSubmitted(true);
      void load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not submit your application.');
    } finally {
      setBusy(false);
    }
  };

  if (!selection) return <LoadingState label="Checking your eligibility…" />;

  if (submitted || existing) {
    return (
      <Screen>
        <SectionTitle>Your application</SectionTitle>
        <Banner
          tone="success"
          title="Application submitted"
          message="Our recruitment team will review it and contact you through the selected-candidates group."
        />
        {existing ? (
          <Card>
            <View style={styles.row}>
              <Text style={styles.rowLabel}>Status</Text>
              <Badge label={existing.status} tone="info" />
            </View>
          </Card>
        ) : null}
        <AdBanner />
      </Screen>
    );
  }

  if (!selection.qualified) {
    return (
      <Screen>
        <SectionTitle hint="Both targets must be complete before the form opens.">
          Apply for a job
        </SectionTitle>

        <Banner
          tone="warning"
          title="Not eligible yet"
          message="Finish both targets below to unlock your application."
        />

        {progress ? (
          <Card>
            <Text style={styles.blockTitle}>Referrals</Text>
            <ProgressBar
              current={progress.referrals.completed}
              total={progress.referrals.required}
            />
            <Text style={styles.blockCaption}>
              {progress.referrals.completed} of {progress.referrals.required} verified
            </Text>

            <View style={styles.divider} />

            <Text style={styles.blockTitle}>KYC training</Text>
            <ProgressBar
              current={progress.kycChallenges.completed}
              total={progress.kycChallenges.required}
            />
            <Text style={styles.blockCaption}>
              {progress.kycChallenges.completed} of {progress.kycChallenges.required} completed
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
      <SectionTitle hint="You have met both targets.">Apply for a job</SectionTitle>

      {error ? <Banner tone="danger" title="Could not submit" message={error} /> : null}

      <Card>
        <Text style={styles.pickerLabel}>PREFERRED STATE</Text>
        <View style={styles.chipWrap}>
          {STATES.map((s) => (
            <Pressable
              key={s}
              accessibilityRole="radio"
              accessibilityState={{ selected: state === s }}
              onPress={() => setState(s)}
              style={[styles.chip, state === s ? styles.chipActive : null]}
            >
              <Text style={[styles.chipText, state === s ? styles.chipTextActive : null]}>{s}</Text>
            </Pressable>
          ))}
        </View>

        <Text style={styles.pickerLabel}>PREFERRED TIER</Text>
        <View style={styles.chipWrap}>
          {TIERS.map((t) => (
            <Pressable
              key={t.value}
              accessibilityRole="radio"
              accessibilityState={{ selected: tier === t.value }}
              onPress={() => setTier(t.value)}
              style={[styles.chip, tier === t.value ? styles.chipActive : null]}
            >
              <Text style={[styles.chipText, tier === t.value ? styles.chipTextActive : null]}>
                {t.label}
              </Text>
            </Pressable>
          ))}
        </View>

        <Field
          label="District (optional)"
          value={district}
          onChangeText={setDistrict}
          placeholder="Your preferred district"
          autoCapitalize="characters"
        />

        <Button label="Submit application" onPress={submit} loading={busy} />
      </Card>

      <Banner
        tone="info"
        title="You can apply once"
        message="Choose carefully — each candidate may submit a single application."
      />
      <AdBanner />
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  rowLabel: { ...typography.body, color: colors.textSecondary },

  blockTitle: { ...typography.bodyStrong, color: colors.textPrimary },
  blockCaption: { ...typography.caption, color: colors.textSecondary },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.sm },

  pickerLabel: { ...typography.label, color: colors.textSecondary },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceAlt,
  },
  chipActive: { backgroundColor: colors.brandNavy },
  chipText: { ...typography.caption, color: colors.textSecondary, fontWeight: '600' },
  chipTextActive: { color: colors.textOnBrand },
});
