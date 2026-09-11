import React, { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { api, ApiError, Vacancy } from '../api/client';
import { AdBanner } from '../components/AdBanner';
import { Badge, Banner, Button, Card, EmptyState, LoadingState, Screen, SectionTitle } from '../components/ui';
import { brand, colors, spacing, typography } from '../theme/tokens';

/**
 * Landing screen. Public by design — a visitor who has never signed up must be
 * able to read what the job is and how the process works before creating an
 * account.
 */
export function HomeScreen({
  onSignIn,
  onApply,
  isSignedIn,
}: {
  onSignIn: () => void;
  onApply: () => void;
  isSignedIn: boolean;
}) {
  const [vacancies, setVacancies] = useState<Vacancy[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const { vacancies: list } = await api.vacancies();
      setVacancies(list);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load vacancies.');
      setVacancies([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Screen>
      <Card tone="brand" style={styles.hero}>
        <Text style={styles.heroEyebrow}>{brand.legalName}</Text>
        <Text style={styles.heroTitle}>Retail outlet hiring, now open</Text>
        <Text style={styles.heroBody}>{brand.tagline}</Text>
        {!isSignedIn ? (
          <Button label="Sign up or log in" onPress={onSignIn} variant="secondary" />
        ) : (
          <Button label="Go to application" onPress={onApply} variant="secondary" />
        )}
      </Card>

      <SectionTitle hint="Every step is checked on our servers before it counts.">
        How to apply
      </SectionTitle>

      <Card>
        {HOW_TO_APPLY.map((step, index) => (
          <View key={step.title} style={styles.stepRow}>
            <View style={styles.stepNumber}>
              <Text style={styles.stepNumberText}>{index + 1}</Text>
            </View>
            <View style={styles.stepText}>
              <Text style={styles.stepTitle}>{step.title}</Text>
              <Text style={styles.stepBody}>{step.body}</Text>
            </View>
          </View>
        ))}
      </Card>

      <AdBanner />

      <SectionTitle hint="Openings are filled state by state.">Current vacancies</SectionTitle>

      {error ? <Banner tone="danger" title="Could not load vacancies" message={error} /> : null}

      {vacancies === null ? (
        <LoadingState label="Loading vacancies…" />
      ) : vacancies.length === 0 ? (
        <EmptyState
          title="No openings listed right now"
          message="New positions are posted here as they open. Check back soon."
        />
      ) : (
        vacancies.map((v) => (
          <Card key={v.id}>
            <View style={styles.vacancyHead}>
              <Text style={styles.vacancyTitle}>{v.title}</Text>
              <Badge label={v.tier.toUpperCase()} tone="info" />
            </View>
            <Text style={styles.vacancyMeta}>{v.state}</Text>
            <View style={styles.vacancyFacts}>
              <View style={styles.vacancyFact}>
                <Text style={styles.factValue}>{v.postCount}</Text>
                <Text style={styles.factLabel}>posts</Text>
              </View>
              <View style={styles.vacancyFact}>
                <Text style={styles.factValue}>
                  ₹{v.salaryMonthlyRupees.toLocaleString('en-IN')}
                </Text>
                <Text style={styles.factLabel}>per month</Text>
              </View>
            </View>
          </Card>
        ))
      )}

      <Text style={styles.legal}>
        {brand.legalName}. Identity checks are carried out by a licensed verification provider.
        We never ask you to share another person&apos;s identity documents.
      </Text>
    </Screen>
  );
}

const HOW_TO_APPLY = [
  {
    title: 'Create your account',
    body: 'Sign up with your Aadhaar number, the mobile number linked to it, and a password.',
  },
  {
    title: 'Verify on Telegram',
    body: 'Message our bot, share your contact so we can confirm the number is yours, and join both channels.',
  },
  {
    title: 'Build your referrals',
    body: 'Share your referral link. A referral counts once that person completes their own verification.',
  },
  {
    title: 'Complete KYC training',
    body: 'Work through practice documents and spot the problems in them. All practice documents are fictitious.',
  },
  {
    title: 'Apply and join the group',
    body: 'Once both targets are met, your application opens and you get the selected-candidates group link.',
  },
];

const styles = StyleSheet.create({
  hero: { gap: spacing.md },
  heroEyebrow: { ...typography.label, color: colors.brandGold, textTransform: 'uppercase' },
  heroTitle: { ...typography.display, color: colors.textOnBrand },
  heroBody: { ...typography.body, color: colors.brandGoldSoft },

  stepRow: { flexDirection: 'row', gap: spacing.md, alignItems: 'flex-start' },
  stepNumber: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.brandGoldSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepNumberText: { ...typography.caption, fontWeight: '700', color: colors.brandDeep },
  stepText: { flex: 1, gap: 2 },
  stepTitle: { ...typography.bodyStrong, color: colors.textPrimary },
  stepBody: { ...typography.caption, color: colors.textSecondary },

  vacancyHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.sm },
  vacancyTitle: { ...typography.heading, color: colors.textPrimary, flexShrink: 1 },
  vacancyMeta: { ...typography.caption, color: colors.textSecondary },
  vacancyFacts: { flexDirection: 'row', gap: spacing.xl },
  vacancyFact: { gap: 2 },
  factValue: { ...typography.bodyStrong, color: colors.textPrimary },
  factLabel: { ...typography.caption, color: colors.textMuted },

  legal: { ...typography.caption, color: colors.textMuted, textAlign: 'center' },
});
