import React, { useCallback, useEffect, useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import * as Linking from 'expo-linking';
import { StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { initialiseAds } from './src/ads/init';
import { api, ApiError, Me } from './src/api/client';
import { BrandHeader, NavItem, NavKey } from './src/components/BrandHeader';
import { LoadingState } from './src/components/ui';
import { AccountScreen } from './src/screens/AccountScreen';
import { ApplyScreen } from './src/screens/ApplyScreen';
import { AuthScreen } from './src/screens/AuthScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import { ReferralScreen } from './src/screens/ReferralScreen';
import { SelectedScreen } from './src/screens/SelectedScreen';
import { TrainingScreen } from './src/screens/TrainingScreen';
import { colors } from './src/theme/tokens';

/**
 * App shell.
 *
 * Navigation is the card row in BrandHeader rather than a tab bar, so the row
 * can scroll horizontally and carry per-card captions and badges.
 *
 * The `locked` flag on a card is cosmetic only. Authorisation lives entirely
 * on the server — an unlocked card just produces a 403 — which is the right
 * assumption for an APK anyone can unpack.
 */
export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [booting, setBooting] = useState(true);
  const [active, setActive] = useState<NavKey>('Home');
  const [referralFromLink, setReferralFromLink] = useState<string | null>(null);
  const [showAuth, setShowAuth] = useState(false);

  // Pull ?ref= off the deep link that opened the app, so the signup form can
  // pre-fill and lock it.
  useEffect(() => {
    void (async () => {
      const url = await Linking.getInitialURL();
      if (!url) return;
      const { queryParams } = Linking.parse(url);
      const ref = queryParams?.ref;
      if (typeof ref === 'string' && ref.trim()) setReferralFromLink(ref.trim().toUpperCase());
    })();
  }, []);

  useEffect(() => {
    initialiseAds();
  }, []);

  const refreshSession = useCallback(async () => {
    try {
      setMe(await api.me());
      setShowAuth(false);
    } catch (e) {
      if (e instanceof ApiError && e.isUnauthenticated) setMe(null);
    } finally {
      setBooting(false);
    }
  }, []);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  // Signup was requested via a referral link and there is no session — open
  // the auth screen straight away, as the brief asks.
  useEffect(() => {
    if (!booting && !me && referralFromLink) setShowAuth(true);
  }, [booting, me, referralFromLink]);

  if (booting) {
    return (
      <SafeAreaProvider>
        <View style={styles.bootRoot}>
          <LoadingState label="Starting BBAZAAR…" />
        </View>
      </SafeAreaProvider>
    );
  }

  const signedIn = !!me;
  const verified = signedIn && !['TELEGRAM_PENDING', 'GROUP_PENDING'].includes(me!.status);
  const eligible =
    signedIn &&
    ['APPLICATION_ELIGIBLE', 'APPLIED', 'TRAINING_SCHEDULED', 'TRAINING_ATTENDED', 'HIRED'].includes(
      me!.status,
    );

  const navItems: NavItem[] = [
    { key: 'Home', label: 'Home', caption: 'Vacancies & how to apply' },
    { key: 'Apply', label: 'Apply', caption: eligible ? 'Your application' : 'Unlocks at both targets', locked: !eligible },
    { key: 'Referrals', label: 'Referrals', caption: 'Your link and progress', locked: !verified },
    { key: 'Training', label: 'KYC Training', caption: 'Practice numbers', locked: !verified },
    { key: 'Selected', label: 'Selected', caption: eligible ? 'Group invite ready' : 'Unlocks when selected', locked: !eligible },
    {
      key: 'Account',
      label: signedIn ? 'Account' : 'Sign in',
      caption: signedIn ? (verified ? 'Verified' : 'Finish verification') : 'Sign up or log in',
      badge: signedIn && !verified ? '!' : null,
    },
  ];

  const requireAuth = (node: React.ReactNode) =>
    signedIn ? (
      node
    ) : (
      <AuthScreen
        onAuthenticated={refreshSession}
        onSignedUp={() => setActive('Account')}
        lockedReferralCode={referralFromLink}
      />
    );

  const body = () => {
    if (showAuth && !signedIn) {
      return (
        <AuthScreen
          onAuthenticated={refreshSession}
          onSignedUp={() => setActive('Account')}
          lockedReferralCode={referralFromLink}
        />
      );
    }

    switch (active) {
      case 'Home':
        return (
          <HomeScreen
            isSignedIn={signedIn}
            onSignIn={() => {
              setShowAuth(true);
              setActive('Account');
            }}
            onApply={() => setActive('Apply')}
          />
        );
      case 'Apply':
        return requireAuth(<ApplyScreen onGoToReferrals={() => setActive('Referrals')} />);
      case 'Referrals':
        return requireAuth(<ReferralScreen />);
      case 'Training':
        return requireAuth(<TrainingScreen />);
      case 'Selected':
        return requireAuth(<SelectedScreen onGoToReferrals={() => setActive('Referrals')} />);
      case 'Account':
        return requireAuth(
          <AccountScreen
            onSignedOut={() => {
              setMe(null);
              setActive('Home');
            }}
          />,
        );
      default:
        return null;
    }
  };

  return (
    <SafeAreaProvider>
      <View style={styles.root}>
        <StatusBar style="light" />
        <BrandHeader
          items={navItems}
          activeKey={active}
          onSelect={(key) => {
            setShowAuth(false);
            setActive(key);
          }}
          subtitle={signedIn && !verified ? 'Finish Telegram verification' : undefined}
        />
        <View style={styles.body}>{body()}</View>
      </View>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background },
  bootRoot: { flex: 1, backgroundColor: colors.background, justifyContent: 'center' },
  body: { flex: 1 },
});
