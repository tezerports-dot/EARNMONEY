/**
 * BBAZAAR group of companies — design tokens.
 *
 * Every screen reads colour, spacing, radius and type from here, so a design
 * pass can restyle the whole app by editing this one file. Nothing below is
 * referenced by the backend; it is presentation only.
 */

export const colors = {
  // Brand
  brandDeep: '#0B1F3A',
  brandNavy: '#12325C',
  brandGold: '#D4A24C',
  brandGoldSoft: '#F2E2C4',

  // Surfaces
  background: '#F6F7F9',
  surface: '#FFFFFF',
  surfaceAlt: '#EEF1F5',
  overlay: 'rgba(11, 31, 58, 0.6)',

  // Text
  textPrimary: '#101828',
  textSecondary: '#5A6472',
  textMuted: '#98A2B3',
  textOnBrand: '#FFFFFF',

  // Status — used by the referral and verification screens
  success: '#12805C',
  successSoft: '#E3F5EE',
  warning: '#B54708',
  warningSoft: '#FEF0C7',
  danger: '#B42318',
  dangerSoft: '#FEE4E2',
  info: '#175CD3',
  infoSoft: '#E0EDFF',

  border: '#D7DDE5',
  borderStrong: '#B4BECC',
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  pill: 999,
} as const;

export const typography = {
  display: { fontSize: 28, fontWeight: '700' as const, letterSpacing: -0.4 },
  title: { fontSize: 22, fontWeight: '700' as const, letterSpacing: -0.2 },
  heading: { fontSize: 18, fontWeight: '600' as const },
  body: { fontSize: 15, fontWeight: '400' as const, lineHeight: 22 },
  bodyStrong: { fontSize: 15, fontWeight: '600' as const },
  caption: { fontSize: 13, fontWeight: '400' as const },
  label: { fontSize: 12, fontWeight: '600' as const, letterSpacing: 0.6 },
  numeric: { fontSize: 26, fontWeight: '700' as const },
} as const;

export const shadow = {
  card: {
    shadowColor: '#0B1F3A',
    shadowOpacity: 0.08,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 3,
  },
  raised: {
    shadowColor: '#0B1F3A',
    shadowOpacity: 0.16,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 8 },
    elevation: 6,
  },
} as const;

export const brand = {
  name: 'BBAZAAR',
  legalName: 'BBAZAAR group of companies',
  tagline: 'Retail careers, earned through your network',
} as const;
