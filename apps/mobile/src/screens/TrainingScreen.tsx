import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { api, ApiError, Challenge, ChallengeResult, KycIssue, ReferralSummary } from '../api/client';
import { AdBanner } from '../components/AdBanner';
import {
  Badge, Banner, Button, Card, LoadingState, ProgressBar, Screen, SectionTitle,
} from '../components/ui';
import { colors, radius, spacing, typography } from '../theme/tokens';

/**
 * KYC competency training.
 *
 * Important: every document shown here is FICTITIOUS and authored by the
 * company. No real person's identity details are ever routed through another
 * candidate — see docs/SPEC-DEVIATIONS.md for why that was ruled out. The task
 * tests whether the candidate can spot a problem in a document, which is the
 * actual on-the-job skill.
 *
 * Grading happens server-side; the correct answer is not in the payload the
 * app receives until after submission.
 */
export function TrainingScreen() {
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [progress, setProgress] = useState<ReferralSummary['progress'] | null>(null);
  const [result, setResult] = useState<ChallengeResult | null>(null);
  const [issues, setIssues] = useState<KycIssue[]>([]);
  const [selectedIssue, setSelectedIssue] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exhausted, setExhausted] = useState(false);

  const loadProgress = useCallback(async () => {
    try {
      const summary = await api.referrals();
      setProgress(summary.progress);
    } catch {
      // Progress is decoration here; a failure must not block the task.
    }
  }, []);

  const loadIssues = useCallback(async () => {
    try {
      const { issues: list } = await api.kycIssues();
      setIssues(list);
    } catch {
      // The picker is the only way to answer, so a failure here is retried on
      // the next challenge rather than silently leaving an empty list.
    }
  }, []);

  const loadChallenge = useCallback(async () => {
    setError(null);
    setResult(null);
    setSelectedIssue(null);
    setExhausted(false);
    try {
      setChallenge(await api.nextChallenge());
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) {
        setExhausted(true);
        setChallenge(null);
        return;
      }
      setError(e instanceof ApiError ? e.message : 'Could not load a practice document.');
    }
  }, []);

  useEffect(() => {
    void loadChallenge();
    void loadProgress();
    void loadIssues();
  }, [loadChallenge, loadProgress, loadIssues]);

  const submit = async (valid: boolean) => {
    if (!challenge) return;
    setBusy(true);
    setError(null);
    try {
      const outcome = await api.submitChallenge(challenge.attemptId, {
        valid,
        issue: valid ? undefined : (selectedIssue ?? undefined),
      });
      setResult(outcome);
      void loadProgress();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not submit your answer.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <SectionTitle hint="Practice documents only — none of these are real people.">
        KYC training
      </SectionTitle>

      {progress ? (
        <Card>
          <View style={styles.progressHead}>
            <Text style={styles.progressTitle}>
              {progress.kycChallenges.completed} of {progress.kycChallenges.required} completed
            </Text>
            <Badge
              label={
                progress.kycChallenges.completed >= progress.kycChallenges.required
                  ? 'Target met'
                  : `${progress.kycChallenges.required - progress.kycChallenges.completed} to go`
              }
              tone={
                progress.kycChallenges.completed >= progress.kycChallenges.required
                  ? 'success'
                  : 'default'
              }
            />
          </View>
          <ProgressBar
            current={progress.kycChallenges.completed}
            total={progress.kycChallenges.required}
          />
        </Card>
      ) : null}

      {error ? <Banner tone="danger" title="Something went wrong" message={error} /> : null}

      {exhausted ? (
        <Banner
          tone="info"
          title="No new practice documents right now"
          message="You have worked through everything currently available. More are added regularly."
        />
      ) : null}

      {result ? (
        <>
          <Banner
            tone={result.correct ? 'success' : 'warning'}
            title={result.correct ? 'Correct' : 'Not quite'}
            message={
              result.correctOutcome.valid
                ? 'This document was genuine — nothing was wrong with it.'
                : `The problem was: ${result.correctOutcome.issue ?? 'a mismatch in the details'}.`
            }
          />
          {result.promotedToApplicationEligible ? (
            <Banner
              tone="success"
              title="You are now eligible to apply"
              message="Both targets are complete. Head to the Apply screen."
            />
          ) : null}
          <Button label="Next document" onPress={loadChallenge} />
        </>
      ) : challenge ? (
        <>
          <Card>
            <Text style={styles.challengeTitle}>{challenge.title}</Text>
            <View style={styles.documentBox}>
              {Object.entries(challenge.document).map(([key, value]) => (
                <View key={key} style={styles.docRow}>
                  <Text style={styles.docKey}>{humanise(key)}</Text>
                  <Text style={styles.docValue}>{String(value)}</Text>
                </View>
              ))}
            </View>
            <Text style={styles.helpText}>
              Review the details above. Does everything match and look genuine?
            </Text>
          </Card>

          <Card>
            <Text style={styles.answerLabel}>What is wrong with it?</Text>
            <View style={styles.issueWrap}>
              {issues.map((opt) => {
                const active = selectedIssue === opt.code;
                return (
                  <Pressable
                    key={opt.code}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: active }}
                    onPress={() => setSelectedIssue(active ? null : opt.code)}
                    style={[styles.issueChip, active ? styles.issueChipActive : null]}
                  >
                    <Text style={[styles.issueText, active ? styles.issueTextActive : null]}>
                      {opt.label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            <Text style={styles.helpText}>
              Pick the fault, then tap &quot;Something is wrong&quot;. If the document is fine,
              tap &quot;Looks genuine&quot; instead.
            </Text>
            <View style={styles.answerRow}>
              <Button
                label="Looks genuine"
                onPress={() => submit(true)}
                variant="ghost"
                loading={busy}
                style={styles.answerButton}
              />
              <Button
                label="Something is wrong"
                onPress={() => submit(false)}
                loading={busy}
                // Cannot report a fault without naming it — the grader needs a
                // code, and a blank answer would always be marked wrong.
                disabled={!selectedIssue}
                style={styles.answerButton}
              />
            </View>
          </Card>
        </>
      ) : !exhausted && !error ? (
        <LoadingState label="Loading a practice document…" />
      ) : null}

      <AdBanner />
    </Screen>
  );
}

/** camelCase key -> readable label. */
function humanise(key: string): string {
  return key
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, (c) => c.toUpperCase())
    .trim();
}

const styles = StyleSheet.create({
  progressHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  progressTitle: { ...typography.heading, color: colors.textPrimary },

  challengeTitle: { ...typography.heading, color: colors.textPrimary },
  documentBox: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  docRow: { flexDirection: 'row', justifyContent: 'space-between', gap: spacing.md },
  docKey: { ...typography.caption, color: colors.textSecondary, flexShrink: 0 },
  docValue: { ...typography.bodyStrong, color: colors.textPrimary, flexShrink: 1, textAlign: 'right' },
  helpText: { ...typography.caption, color: colors.textSecondary },

  answerLabel: { ...typography.label, color: colors.textSecondary },
  issueWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  issueChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceAlt,
  },
  issueChipActive: { backgroundColor: colors.brandNavy },
  issueText: { ...typography.caption, color: colors.textSecondary, fontWeight: '600' },
  issueTextActive: { color: colors.textOnBrand },
  answerRow: { flexDirection: 'row', gap: spacing.md },
  answerButton: { flex: 1 },
});
