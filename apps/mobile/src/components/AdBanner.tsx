import React from 'react';
import { StyleSheet, View } from 'react-native';
import { BannerAd, BannerAdSize, TestIds } from 'react-native-google-mobile-ads';
import { spacing } from '../theme/tokens';

/**
 * AdMob banner (native builds only — see AdBanner.web.tsx for the web build).
 *
 * `TestIds.ADAPTIVE_BANNER` is used in development builds. Serving real ads
 * from a debug build is what gets AdMob accounts suspended, so the unit id is
 * chosen by __DEV__ rather than by a flag someone can forget to flip.
 *
 * Replace PRODUCTION_BANNER_UNIT_ID with the unit from your AdMob console.
 * Note the policy line to keep on the right side of: ads must not sit where a
 * user could tap them by accident, so this never renders inside or directly
 * under a primary action.
 */
const PRODUCTION_BANNER_UNIT_ID = 'ca-app-pub-0000000000000000/0000000000';

export function AdBanner() {
  const unitId = __DEV__ ? TestIds.ADAPTIVE_BANNER : PRODUCTION_BANNER_UNIT_ID;

  return (
    <View style={styles.wrap}>
      <BannerAd
        unitId={unitId}
        size={BannerAdSize.ANCHORED_ADAPTIVE_BANNER}
        requestOptions={{ requestNonPersonalizedAdsOnly: true }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', paddingVertical: spacing.sm },
});
