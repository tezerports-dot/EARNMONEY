import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { api, ApiError } from '../api/client';
import { Banner, Button, Card, Field, Screen, SectionTitle } from '../components/ui';
import { brand, colors, spacing, typography } from '../theme/tokens';

/**
 * Signup and login. Opens automatically whenever there is no session.
 *
 * A referral code that arrived on the deep link is passed in as
 * `lockedReferralCode` and rendered read-only, so it cannot be swapped for
 * someone else's. The server resolves the code again on its side regardless —
 * this field is a convenience, not the control.
 *
 * Client-side validation here exists to give fast feedback. Every rule is
 * enforced again on the server, which is the only copy that matters.
 */
export function AuthScreen({
  onAuthenticated,
  onSignedUp,
  lockedReferralCode,
}: {
  onAuthenticated: () => void;
  onSignedUp: (referralCode: string) => void;
  lockedReferralCode?: string | null;
}) {
  const [mode, setMode] = useState<'signup' | 'login'>(lockedReferralCode ? 'signup' : 'login');
  const [aadhaar, setAadhaar] = useState('');
  const [mobile, setMobile] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [referralCode, setReferralCode] = useState(lockedReferralCode ?? '');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const reset = () => {
    setError(null);
    setNotice(null);
  };

  const submitSignup = async () => {
    reset();
    const digits = aadhaar.replace(/\D/g, '');
    if (digits.length !== 12) return setError('Enter the full 12-digit Aadhaar number.');
    if (!/^\+?[1-9]\d{9,14}$/.test(mobile.replace(/\s/g, '')))
      return setError('Enter the mobile number linked to that Aadhaar, including country code.');
    if (password !== confirmPassword) return setError('The two passwords do not match.');
    if (password.length < 10) return setError('Password must be at least 10 characters.');
    if (!consent) return setError('Please accept the privacy notice to continue.');

    setBusy(true);
    try {
      const result = await api.signup({
        aadhaarNumber: digits,
        mobile: mobile.startsWith('+') ? mobile : `+${mobile.replace(/\D/g, '')}`,
        password,
        confirmPassword,
        referralCode: referralCode.trim() || undefined,
        consentAccepted: true,
        // Wired to a real CAPTCHA widget before launch; the server rejects
        // signups outright once TURNSTILE_SECRET_KEY is configured.
        captchaToken: 'app',
      });
      onSignedUp(result.referralCode);
      setNotice('Account created. Now verify on Telegram to activate it.');
      setMode('login');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not create your account.');
    } finally {
      setBusy(false);
    }
  };

  const submitLogin = async () => {
    reset();
    setBusy(true);
    try {
      await api.login({
        mobile: mobile.startsWith('+') ? mobile : `+${mobile.replace(/\D/g, '')}`,
        password,
        captchaToken: 'app',
      });
      onAuthenticated();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not sign you in.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <SectionTitle hint={brand.legalName}>
        {mode === 'signup' ? 'Create your account' : 'Welcome back'}
      </SectionTitle>

      <View style={styles.switchRow}>
        <Pressable
          accessibilityRole="tab"
          accessibilityState={{ selected: mode === 'login' }}
          onPress={() => {
            setMode('login');
            reset();
          }}
          style={[styles.switchTab, mode === 'login' ? styles.switchTabActive : null]}
        >
          <Text style={[styles.switchText, mode === 'login' ? styles.switchTextActive : null]}>
            Log in
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="tab"
          accessibilityState={{ selected: mode === 'signup' }}
          onPress={() => {
            setMode('signup');
            reset();
          }}
          style={[styles.switchTab, mode === 'signup' ? styles.switchTabActive : null]}
        >
          <Text style={[styles.switchText, mode === 'signup' ? styles.switchTextActive : null]}>
            Sign up
          </Text>
        </Pressable>
      </View>

      {notice ? <Banner tone="success" title={notice} /> : null}
      {error ? <Banner tone="danger" title="Please check the form" message={error} /> : null}

      <Card>
        {mode === 'signup' ? (
          <Field
            label="Aadhaar number"
            value={aadhaar}
            onChangeText={setAadhaar}
            placeholder="1234 5678 9012"
            keyboardType="number-pad"
            maxLength={14}
            hint="Stored only as a one-way hash. We never show or share it."
          />
        ) : null}

        <Field
          label="Mobile number"
          value={mobile}
          onChangeText={setMobile}
          placeholder="+91 98765 43210"
          keyboardType="phone-pad"
          hint={mode === 'signup' ? 'Must be the number linked to your Aadhaar.' : undefined}
        />

        <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry />

        {mode === 'signup' ? (
          <>
            <Field
              label="Confirm password"
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              secureTextEntry
            />
            <Field
              label="Referral code"
              value={referralCode}
              onChangeText={setReferralCode}
              placeholder="Optional"
              autoCapitalize="characters"
              editable={!lockedReferralCode}
              hint={
                lockedReferralCode
                  ? 'Filled from the link you opened, and locked.'
                  : 'Leave blank if nobody referred you.'
              }
            />

            <Pressable
              accessibilityRole="checkbox"
              accessibilityState={{ checked: consent }}
              onPress={() => setConsent((c) => !c)}
              style={styles.consentRow}
            >
              <View style={[styles.checkbox, consent ? styles.checkboxOn : null]}>
                {consent ? <Text style={styles.checkboxMark}>✓</Text> : null}
              </View>
              <Text style={styles.consentText}>
                I agree to {brand.legalName} processing my details for this recruitment process.
              </Text>
            </Pressable>
          </>
        ) : null}

        <Button
          label={mode === 'signup' ? 'Create account' : 'Log in'}
          onPress={mode === 'signup' ? submitSignup : submitLogin}
          loading={busy}
        />
      </Card>

      {mode === 'signup' ? (
        <Banner
          tone="info"
          title="One account per person"
          message="Each Aadhaar number can hold exactly one account. After signing up you will verify on Telegram before the account activates."
        />
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  switchRow: { flexDirection: 'row', backgroundColor: colors.surfaceAlt, borderRadius: 12, padding: 4, gap: 4 },
  switchTab: { flex: 1, paddingVertical: spacing.sm, borderRadius: 10, alignItems: 'center' },
  switchTabActive: { backgroundColor: colors.surface },
  switchText: { ...typography.bodyStrong, color: colors.textSecondary },
  switchTextActive: { color: colors.brandDeep },

  consentRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxOn: { backgroundColor: colors.brandNavy, borderColor: colors.brandNavy },
  checkboxMark: { color: colors.textOnBrand, fontSize: 14, fontWeight: '700' },
  consentText: { ...typography.caption, color: colors.textSecondary, flex: 1 },
});
