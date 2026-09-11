import React, { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';
import { api, ApiError, Challenge, ChallengeResult, ReferralSummary } from '../api/client';
import { AdBanner } from '../components/AdBanner';
import {
  Badge, Banner, Button, Card, LoadingState, ProgressBar, Screen, SectionTitle,
} from '../components/ui';
import { colors, radius, spacing, typography } from '../theme/tokens';

/**
 * Number-reading training.
 *
 * A 12-digit number is shown, one question is asked about it, and the
 * candidate types the answer. That is the whole task: it checks whether
 * someone can read an Aadhaar-format number accurately, which is the skill
 * the job actually needs.
 *
 * Every number is GENERATED, never a real person's — see
 * docs/SPEC-DEVIATIONS.md. That is both the legal position and the practical
 * one: generated numbers mean an unlimited supply of questions and a grader
 * that always knows the right answer, so any target the admin sets is
 * reachable.
 *
 * Grading is server-side. The correct answer is not in the payload the app
 * receives until after the candidate has submitted.
 */
export function TrainingScreen() {
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [progress, setProgress] = useState<ReferralSummary['progress'] | null>(null);
  const [result, setResult] = useState<ChallengeResult | null>(null);
  const [answer, setAnswer] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadProgress = useCallback(async () => {
    try {
      const summary = await api.referrals();
      setProgress(summary.progress);
    } catch {
      // Progress is decoration here; a failure must not block the task.
    }
  }, []);

  const loadChallenge = useCallback(async () => {
    setError(null);
    setResult(null);
    setAnswer('');
    try {
      setChallenge(await api.nextChallenge());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load a practice number.');
    }
  }, []);

  useEffect(() => {
    void loadChallenge();
    void loadProgress();
  }, [loadChallenge, loadProgress]);

  const submit = async () => {
    if (!challenge || !answer.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const outcome = await api.submitChallenge(challenge.attemptId, answer.trim());
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
      <SectionTitle hint="Practice numbers only — none of these belong to a real person.">
        Number reading
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

      {result ? (
        <>
          <Banner
            tone={result.correct ? 'success' : 'warning'}
            title={result.correct ? 'Correct' : 'Not quite'}
            message={
              result.correct
                ? 'You read the number accurately.'
                : `The correct answer was ${result.correctAnswer}. Read the number one group at a time.`
            }
          />
          {result.promotedToApplicationEligible ? (
            <Banner
              tone="success"
              title="You are now eligible to apply"
              message="Both targets are complete. Head to the Apply screen."
            />
          ) : null}
          <Button label="Next number" onPress={loadChallenge} />
        </>
      ) : challenge ? (
        <>
          <Card>
            <Text style={styles.numberLabel}>Read this number</Text>
            <View style={styles.numberBox}>
              {/* Selection is off so the number cannot be copy-pasted into the
                  answer box, which would skip the reading entirely. */}
              <Text style={styles.number} selectable={false}>
                {challenge.numberDisplay}
              </Text>
            </View>
          </Card>

          <Card>
            <Text style={styles.question}>{challenge.question}</Text>
            <TextInput
              value={answer}
              onChangeText={setAnswer}
              keyboardType="number-pad"
              // The answer is always digits, so a numeric pad is faster and
              // rules out a whole class of typos.
              inputMode="numeric"
              maxLength={20}
              autoCorrect={false}
              placeholder={challenge.answerHint}
              placeholderTextColor={colors.textSecondary}
              style={styles.input}
              accessibilityLabel={challenge.question}
              onSubmitEditing={submit}
              returnKeyType="done"
            />
            <Button
              label="Submit answer"
              onPress={submit}
              loading={busy}
              // A blank answer is always wrong, so it would only burn an
              // attempt.
              disabled={!answer.trim()}
            />
          </Card>
        </>
      ) : !error ? (
        <LoadingState label="Loading a practice number…" />
      ) : null}

      <AdBanner />
    </Screen>
  );
}

const styles = StyleSheet.create({
  progressHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  progressTitle: { ...typography.heading, color: colors.textPrimary },

  numberLabel: { ...typography.label, color: colors.textSecondary },
  numberBox: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.md,
    alignItems: 'center',
  },
  number: {
    ...typography.heading,
    color: colors.textPrimary,
    fontSize: 28,
    lineHeight: 36,
    // Monospaced digits keep the groups evenly spaced, so nothing is
    // misread because of uneven letterforms.
    fontVariant: ['tabular-nums'],
    letterSpacing: 2,
  },

  question: { ...typography.bodyStrong, color: colors.textPrimary },
  input: {
    ...typography.heading,
    color: colors.textPrimary,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    textAlign: 'center',
    letterSpacing: 2,
  },
});
