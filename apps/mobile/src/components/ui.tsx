import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  ViewStyle,
} from 'react-native';
import { colors, radius, shadow, spacing, typography } from '../theme/tokens';

/**
 * Presentational building blocks. No data fetching, no navigation, no business
 * rules — a design pass can restyle anything in this file without touching
 * behaviour.
 */

export function Card({
  children,
  style,
  tone = 'default',
}: {
  children: React.ReactNode;
  style?: ViewStyle;
  tone?: 'default' | 'brand' | 'success' | 'warning' | 'danger';
}) {
  return <View style={[styles.card, toneStyles[tone], style]}>{children}</View>;
}

export function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <View style={styles.sectionTitleWrap}>
      <Text style={styles.sectionTitle}>{children}</Text>
      {hint ? <Text style={styles.sectionHint}>{hint}</Text> : null}
    </View>
  );
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled,
  loading,
  style,
}: {
  label: string;
  onPress?: () => void;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  disabled?: boolean;
  loading?: boolean;
  style?: ViewStyle;
}) {
  const isDisabled = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!isDisabled, busy: !!loading }}
      onPress={isDisabled ? undefined : onPress}
      style={({ pressed }) => [
        styles.button,
        buttonVariants[variant],
        pressed && !isDisabled ? styles.buttonPressed : null,
        isDisabled ? styles.buttonDisabled : null,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={variant === 'primary' ? colors.textOnBrand : colors.brandNavy} />
      ) : (
        <Text style={[styles.buttonLabel, buttonLabelVariants[variant]]}>{label}</Text>
      )}
    </Pressable>
  );
}

export function Field({
  label,
  value,
  onChangeText,
  placeholder,
  secureTextEntry,
  keyboardType,
  autoCapitalize = 'none',
  editable = true,
  maxLength,
  hint,
  error,
}: {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
  placeholder?: string;
  secureTextEntry?: boolean;
  keyboardType?: 'default' | 'number-pad' | 'phone-pad';
  autoCapitalize?: 'none' | 'characters';
  editable?: boolean;
  maxLength?: number;
  hint?: string;
  error?: string | null;
}) {
  return (
    <View style={styles.fieldWrap}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        style={[styles.input, !editable ? styles.inputLocked : null, error ? styles.inputError : null]}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.textMuted}
        secureTextEntry={secureTextEntry}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize}
        autoCorrect={false}
        editable={editable}
        maxLength={maxLength}
      />
      {error ? (
        <Text style={styles.fieldError}>{error}</Text>
      ) : hint ? (
        <Text style={styles.fieldHint}>{hint}</Text>
      ) : null}
    </View>
  );
}

/** Big number + caption. Used across the referral dashboard. */
export function StatTile({
  value,
  label,
  tone = 'default',
}: {
  value: number | string;
  label: string;
  tone?: 'default' | 'success' | 'warning' | 'danger';
}) {
  return (
    <View style={[styles.statTile, statToneStyles[tone]]}>
      <Text style={[styles.statValue, statTextTones[tone]]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

export function ProgressBar({
  current,
  total,
  tone = 'brand',
}: {
  current: number;
  total: number;
  tone?: 'brand' | 'success';
}) {
  const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;
  return (
    <View style={styles.progressOuter} accessibilityRole="progressbar">
      <View
        style={[
          styles.progressInner,
          { width: `${pct}%` },
          tone === 'success' ? { backgroundColor: colors.success } : null,
        ]}
      />
    </View>
  );
}

export function Badge({
  label,
  tone = 'default',
}: {
  label: string;
  tone?: 'default' | 'success' | 'warning' | 'danger' | 'info';
}) {
  return (
    <View style={[styles.badge, badgeTones[tone]]}>
      <Text style={[styles.badgeText, badgeTextTones[tone]]}>{label}</Text>
    </View>
  );
}

/** Checklist row used by the Telegram verification steps. */
export function StepRow({
  done,
  title,
  description,
}: {
  done: boolean;
  title: string;
  description?: string;
}) {
  return (
    <View style={styles.stepRow}>
      <View style={[styles.stepDot, done ? styles.stepDotDone : null]}>
        <Text style={[styles.stepDotText, done ? styles.stepDotTextDone : null]}>
          {done ? '✓' : '•'}
        </Text>
      </View>
      <View style={styles.stepBody}>
        <Text style={[styles.stepTitle, done ? styles.stepTitleDone : null]}>{title}</Text>
        {description ? <Text style={styles.stepDescription}>{description}</Text> : null}
      </View>
    </View>
  );
}

export function Banner({
  tone,
  title,
  message,
}: {
  tone: 'info' | 'success' | 'warning' | 'danger';
  title: string;
  message?: string;
}) {
  return (
    <View style={[styles.banner, bannerTones[tone]]}>
      <Text style={[styles.bannerTitle, bannerTextTones[tone]]}>{title}</Text>
      {message ? <Text style={styles.bannerMessage}>{message}</Text> : null}
    </View>
  );
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <View style={styles.centered}>
      <ActivityIndicator color={colors.brandNavy} size="large" />
      <Text style={styles.centeredText}>{label}</Text>
    </View>
  );
}

export function EmptyState({ title, message }: { title: string; message?: string }) {
  return (
    <View style={styles.centered}>
      <Text style={styles.emptyTitle}>{title}</Text>
      {message ? <Text style={styles.centeredText}>{message}</Text> : null}
    </View>
  );
}

export function Screen({ children }: { children: React.ReactNode }) {
  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.screenContent}
      keyboardShouldPersistTaps="handled"
    >
      {children}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  screenContent: { padding: spacing.lg, paddingBottom: spacing.xxxl, gap: spacing.lg },

  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.md,
    ...shadow.card,
  },

  sectionTitleWrap: { gap: spacing.xs },
  sectionTitle: { ...typography.title, color: colors.textPrimary },
  sectionHint: { ...typography.caption, color: colors.textSecondary },

  button: {
    minHeight: 52,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
  buttonPressed: { opacity: 0.85, transform: [{ scale: 0.99 }] },
  buttonDisabled: { opacity: 0.45 },
  buttonLabel: { ...typography.bodyStrong },

  fieldWrap: { gap: spacing.xs },
  fieldLabel: { ...typography.label, color: colors.textSecondary, textTransform: 'uppercase' },
  input: {
    minHeight: 52,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
    color: colors.textPrimary,
    ...typography.body,
  },
  inputLocked: { backgroundColor: colors.surfaceAlt, color: colors.textSecondary },
  inputError: { borderColor: colors.danger },
  fieldHint: { ...typography.caption, color: colors.textMuted },
  fieldError: { ...typography.caption, color: colors.danger },

  statTile: {
    flex: 1,
    minWidth: 80,
    borderRadius: radius.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceAlt,
    gap: spacing.xs,
  },
  statValue: { ...typography.numeric, color: colors.textPrimary },
  statLabel: { ...typography.caption, color: colors.textSecondary },

  progressOuter: {
    height: 10,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceAlt,
    overflow: 'hidden',
  },
  progressInner: { height: '100%', borderRadius: radius.pill, backgroundColor: colors.brandGold },

  badge: {
    alignSelf: 'flex-start',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceAlt,
  },
  badgeText: { ...typography.caption, fontWeight: '600', color: colors.textSecondary },

  stepRow: { flexDirection: 'row', gap: spacing.md, alignItems: 'flex-start' },
  stepDot: {
    width: 26,
    height: 26,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceAlt,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepDotDone: { backgroundColor: colors.successSoft },
  stepDotText: { ...typography.caption, color: colors.textMuted, fontWeight: '700' },
  stepDotTextDone: { color: colors.success },
  stepBody: { flex: 1, gap: 2 },
  stepTitle: { ...typography.bodyStrong, color: colors.textPrimary },
  stepTitleDone: { color: colors.success },
  stepDescription: { ...typography.caption, color: colors.textSecondary },

  banner: { borderRadius: radius.md, padding: spacing.md, gap: spacing.xs },
  bannerTitle: { ...typography.bodyStrong },
  bannerMessage: { ...typography.caption, color: colors.textSecondary },

  centered: { alignItems: 'center', justifyContent: 'center', padding: spacing.xxl, gap: spacing.sm },
  centeredText: { ...typography.caption, color: colors.textSecondary, textAlign: 'center' },
  emptyTitle: { ...typography.heading, color: colors.textPrimary, textAlign: 'center' },
});

const toneStyles: Record<string, ViewStyle> = {
  default: {},
  brand: { backgroundColor: colors.brandDeep },
  success: { backgroundColor: colors.successSoft },
  warning: { backgroundColor: colors.warningSoft },
  danger: { backgroundColor: colors.dangerSoft },
};

const buttonVariants: Record<string, ViewStyle> = {
  primary: { backgroundColor: colors.brandNavy },
  secondary: { backgroundColor: colors.brandGoldSoft },
  ghost: { backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.border },
  danger: { backgroundColor: colors.dangerSoft },
};

const buttonLabelVariants: Record<string, { color: string }> = {
  primary: { color: colors.textOnBrand },
  secondary: { color: colors.brandDeep },
  ghost: { color: colors.textPrimary },
  danger: { color: colors.danger },
};

const statToneStyles: Record<string, ViewStyle> = {
  default: {},
  success: { backgroundColor: colors.successSoft },
  warning: { backgroundColor: colors.warningSoft },
  danger: { backgroundColor: colors.dangerSoft },
};

const statTextTones: Record<string, { color: string }> = {
  default: { color: colors.textPrimary },
  success: { color: colors.success },
  warning: { color: colors.warning },
  danger: { color: colors.danger },
};

const badgeTones: Record<string, ViewStyle> = {
  default: { backgroundColor: colors.surfaceAlt },
  success: { backgroundColor: colors.successSoft },
  warning: { backgroundColor: colors.warningSoft },
  danger: { backgroundColor: colors.dangerSoft },
  info: { backgroundColor: colors.infoSoft },
};

const badgeTextTones: Record<string, { color: string }> = {
  default: { color: colors.textSecondary },
  success: { color: colors.success },
  warning: { color: colors.warning },
  danger: { color: colors.danger },
  info: { color: colors.info },
};

const bannerTones: Record<string, ViewStyle> = {
  info: { backgroundColor: colors.infoSoft },
  success: { backgroundColor: colors.successSoft },
  warning: { backgroundColor: colors.warningSoft },
  danger: { backgroundColor: colors.dangerSoft },
};

const bannerTextTones: Record<string, { color: string }> = {
  info: { color: colors.info },
  success: { color: colors.success },
  warning: { color: colors.warning },
  danger: { color: colors.danger },
};
