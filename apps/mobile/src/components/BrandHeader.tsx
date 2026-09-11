import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { brand, colors, radius, shadow, spacing, typography } from '../theme/tokens';

export type NavKey = 'Home' | 'Apply' | 'Referrals' | 'Training' | 'Selected' | 'Account';

export type NavItem = {
  key: NavKey;
  label: string;
  /** Short line under the label on the card. */
  caption: string;
  /** Renders a dot on the card — e.g. steps left, or a blocked state. */
  badge?: string | null;
  locked?: boolean;
};

/**
 * The masthead plus the horizontally scrollable row of card buttons that is
 * this app's primary navigation. Cards are wide enough that the row always
 * overflows, which is what makes the swipe affordance obvious.
 *
 * Purely presentational — it reports taps upward and renders what it is told.
 * `locked` only dims a card; the server still refuses the underlying call, so
 * a patched APK gains nothing by unlocking them.
 */
export function BrandHeader({
  items,
  activeKey,
  onSelect,
  subtitle,
}: {
  items: NavItem[];
  activeKey: NavKey;
  onSelect: (key: NavKey) => void;
  subtitle?: string;
}) {
  const insets = useSafeAreaInsets();

  return (
    <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
      <View style={styles.mastheadRow}>
        <View style={styles.logoMark}>
          <Text style={styles.logoMarkText}>BB</Text>
        </View>
        <View style={styles.mastheadText}>
          <Text style={styles.brandName}>{brand.name}</Text>
          <Text style={styles.brandSub} numberOfLines={1}>
            {subtitle ?? brand.legalName}
          </Text>
        </View>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.navRow}
        // Cards snap so the row settles on a card edge rather than mid-card.
        snapToInterval={CARD_WIDTH + spacing.md}
        decelerationRate="fast"
      >
        {items.map((item) => {
          const active = item.key === activeKey;
          return (
            <Pressable
              key={item.key}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              accessibilityLabel={`${item.label}. ${item.caption}`}
              onPress={() => onSelect(item.key)}
              style={({ pressed }) => [
                styles.navCard,
                active ? styles.navCardActive : null,
                item.locked ? styles.navCardLocked : null,
                pressed ? styles.navCardPressed : null,
              ]}
            >
              <View style={styles.navCardTop}>
                <Text style={[styles.navLabel, active ? styles.navLabelActive : null]}>
                  {item.label}
                </Text>
                {item.badge ? (
                  <View style={[styles.navBadge, active ? styles.navBadgeActive : null]}>
                    <Text style={styles.navBadgeText}>{item.badge}</Text>
                  </View>
                ) : null}
              </View>
              <Text
                style={[styles.navCaption, active ? styles.navCaptionActive : null]}
                numberOfLines={2}
              >
                {item.caption}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const CARD_WIDTH = 148;

const styles = StyleSheet.create({
  header: {
    backgroundColor: colors.brandDeep,
    paddingBottom: spacing.md,
    borderBottomLeftRadius: radius.xl,
    borderBottomRightRadius: radius.xl,
    ...shadow.raised,
  },

  mastheadRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  logoMark: {
    width: 42,
    height: 42,
    borderRadius: radius.md,
    backgroundColor: colors.brandGold,
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoMarkText: { ...typography.bodyStrong, color: colors.brandDeep, letterSpacing: 0.5 },
  mastheadText: { flex: 1 },
  brandName: { ...typography.title, color: colors.textOnBrand, letterSpacing: 1.5 },
  brandSub: { ...typography.caption, color: colors.brandGoldSoft },

  navRow: { paddingHorizontal: spacing.lg, gap: spacing.md },
  navCard: {
    width: CARD_WIDTH,
    minHeight: 84,
    borderRadius: radius.md,
    padding: spacing.md,
    backgroundColor: colors.brandNavy,
    justifyContent: 'space-between',
    gap: spacing.xs,
  },
  navCardActive: { backgroundColor: colors.brandGold },
  navCardLocked: { opacity: 0.55 },
  navCardPressed: { transform: [{ scale: 0.97 }] },
  navCardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.xs },
  navLabel: { ...typography.bodyStrong, color: colors.textOnBrand, flexShrink: 1 },
  navLabelActive: { color: colors.brandDeep },
  navCaption: { ...typography.caption, color: colors.brandGoldSoft },
  navCaptionActive: { color: colors.brandDeep },
  navBadge: {
    minWidth: 20,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radius.pill,
    backgroundColor: colors.brandGold,
    alignItems: 'center',
  },
  navBadgeActive: { backgroundColor: colors.brandDeep },
  navBadgeText: { fontSize: 11, fontWeight: '700', color: colors.textOnBrand },
});
