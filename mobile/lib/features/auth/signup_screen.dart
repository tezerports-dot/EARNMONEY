import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/api/api_exception.dart';
import '../../core/auth/session_controller.dart';
import '../../core/config/config_controller.dart';
import '../../core/deep_links/referral_links.dart';
import '../../core/providers.dart';
import '../../core/security/idempotency.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/inputs.dart';
import '../../core/widgets/screen.dart';
import '../../core/widgets/status_chip.dart';
import 'captcha_field.dart';

class SignupScreen extends ConsumerStatefulWidget {
  const SignupScreen({super.key});

  @override
  ConsumerState<SignupScreen> createState() => _SignupScreenState();
}

enum _CodeState { none, checking, valid, invalid, unknown }

class _SignupScreenState extends ConsumerState<SignupScreen> {
  final _phone = TextEditingController();
  final _password = TextEditingController();
  final _code = TextEditingController();
  final _captcha = CaptchaController();
  bool _busy = false;
  String? _phoneError;
  String? _passwordError;
  String? _codeError;
  String? _captchaError;
  String? _formError;
  bool _phoneTaken = false;
  _CodeState _codeState = _CodeState.none;

  // One key per set of inputs: a retry after a network drop reuses it, so
  // the server creates the account at most once.
  String? _idempotencyKey;
  String? _keyFor;

  @override
  void initState() {
    super.initState();
    final pending = ref.read(prefsProvider).pendingReferralCode;
    if (pending != null) {
      _code.text = pending;
      _checkCode();
    }
    _captcha.load(ref.read(apiProvider));
  }

  @override
  void dispose() {
    _phone.dispose();
    _password.dispose();
    _code.dispose();
    _captcha.dispose();
    super.dispose();
  }

  Future<void> _checkCode() async {
    final raw = _code.text.trim();
    if (raw.isEmpty) {
      setState(() => _codeState = _CodeState.none);
      return;
    }
    final code = normalizeReferralCode(raw);
    if (code == null) {
      setState(() => _codeState = _CodeState.invalid);
      return;
    }
    setState(() => _codeState = _CodeState.checking);
    try {
      final valid = await ref.read(apiProvider).referralCodeValid(code);
      if (mounted) setState(() => _codeState = valid ? _CodeState.valid : _CodeState.invalid);
    } on ServerRejection catch (e) {
      if (mounted) {
        setState(() => _codeState = e.code == 'REFERRAL_CODE_INVALID' ? _CodeState.invalid : _CodeState.unknown);
      }
    } on ApiException {
      // Can't check right now; the server checks again at signup.
      if (mounted) setState(() => _codeState = _CodeState.unknown);
    }
  }

  Future<void> _pasteCode() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final code = normalizeReferralCode(data?.text);
    if (code == null) {
      setState(() => _codeState = _CodeState.invalid);
      return;
    }
    _code.text = code;
    await _checkCode();
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    final code = _code.text.trim().isEmpty ? null : normalizeReferralCode(_code.text);
    setState(() {
      _phoneError = Validators.indianMobile(_phone.text);
      _passwordError = Validators.newPassword(_password.text);
      _codeError = _code.text.trim().isNotEmpty && code == null ? 'Referral codes have 8 letters and numbers.' : null;
      _captchaError = _captcha.answer.text.isEmpty ? 'Answer the question.' : null;
      _formError = null;
      _phoneTaken = false;
    });
    final captcha = _captcha.captcha;
    if (_phoneError != null || _passwordError != null || _codeError != null || _captchaError != null) return;
    if (captcha == null) {
      await _captcha.load(ref.read(apiProvider));
      return;
    }

    final signature = '${_phone.text.trim()}|${code ?? ''}';
    if (_keyFor != signature) {
      _idempotencyKey = newIdempotencyKey();
      _keyFor = signature;
    }

    setState(() => _busy = true);
    try {
      await ref
          .read(sessionProvider.notifier)
          .signup(
            phone: _phone.text.trim(),
            password: _password.text,
            referralCode: code,
            captchaId: captcha.id,
            captchaAnswer: _captcha.answer.text,
            idempotencyKey: _idempotencyKey!,
          );
      // Signed in as "pending": the router opens Telegram verification.
    } on ServerRejection catch (e) {
      setState(() {
        switch (e.code) {
          case 'VALIDATION_FAILED':
            _phoneError = e.fields['phone'];
            _passwordError = e.fields['password'];
            _formError = e.fields.isEmpty ? e.message : null;
          case 'REFERRAL_CODE_INVALID':
            _codeError = e.message;
            _codeState = _CodeState.invalid;
          case 'PHONE_UNAVAILABLE':
            _phoneError = e.message;
            _phoneTaken = true;
          case 'CAPTCHA_INVALID' || 'CAPTCHA_REQUIRED':
            _captchaError = e.message;
          default:
            _formError = e.message;
        }
      });
      await _captcha.load(ref.read(apiProvider));
    } on OfflineException catch (e) {
      // Keep the same key: retrying can't create a second account.
      setState(() => _formError = e.userMessage);
    } on ApiException catch (e) {
      setState(() => _formError = e.userMessage);
      await _captcha.load(ref.read(apiProvider));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget? _codeChip() => switch (_codeState) {
    _CodeState.none => null,
    _CodeState.checking => const StatusChip(label: 'Checking code…', tone: StatusTone.neutral),
    _CodeState.valid => const StatusChip(label: 'Valid referral code', tone: StatusTone.success),
    _CodeState.invalid => const StatusChip(label: "This code isn't valid", tone: StatusTone.danger),
    _CodeState.unknown => const StatusChip(label: "Couldn't check the code now", tone: StatusTone.info),
  };

  @override
  Widget build(BuildContext context) {
    final cfg = ref.watch(configProvider).requireValue.config;
    final open = cfg.campaign.signupsOpen;
    final chip = _codeChip();
    return AutofillGroup(
      child: AppScreen(
        showBack: false,
        children: [
          const SizedBox(height: Space.xl),
          Semantics(header: true, child: const Text('Create your account', style: AppType.headline)),
          const SizedBox(height: Space.s),
          Text('Join the ${cfg.companyName} launch. It takes about two minutes.', style: AppType.body),
          const SizedBox(height: Space.xl),
          const GlassCard(
            highlight: true,
            padding: EdgeInsets.all(Space.l),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.send_rounded, color: AppColors.telegram),
                SizedBox(width: Space.m),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Telegram verification is required', style: AppType.label),
                      SizedBox(height: Space.xs),
                      Text(
                        'After signing up you will open our Telegram bot, send join requests to our channels '
                        'and share your Telegram number. It must match the number you enter here.',
                        style: AppType.bodySmall,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: Space.xl),
          if (!open) ...[
            GlassCard(
              child: Text(
                'Sign-ups are closed right now. Please check back later.',
                style: AppType.body.copyWith(color: AppColors.warning),
              ),
            ),
            const SizedBox(height: Space.xl),
          ],
          PhoneField(controller: _phone, errorText: _phoneError),
          if (_phoneTaken)
            Align(
              alignment: Alignment.centerLeft,
              child: LinkButton(label: 'Log in instead', onPressed: () => context.go('/login')),
            ),
          const FieldGap(),
          PasswordField(
            controller: _password,
            errorText: _passwordError,
            newPassword: true,
            helper: 'At least 8 characters. Use one you don’t use anywhere else.',
          ),
          const FieldGap(),
          Focus(
            onFocusChange: (focused) {
              if (!focused) _checkCode();
            },
            child: AppTextField(
              controller: _code,
              label: 'Referral code (optional)',
              hint: 'e.g. 7Q2K9MXA',
              errorText: _codeError,
              prefixIcon: Icons.card_giftcard_rounded,
              textCapitalization: TextCapitalization.characters,
              maxLength: 12,
              suffix: IconButton(
                tooltip: 'Paste code',
                icon: const Icon(Icons.content_paste_rounded),
                onPressed: _pasteCode,
              ),
              onChanged: (value) {
                if (normalizeReferralCode(value) != null) _checkCode();
              },
            ),
          ),
          if (chip != null) ...[const SizedBox(height: Space.s), Align(alignment: Alignment.centerLeft, child: chip)],
          const FieldGap(),
          CaptchaField(controller: _captcha, errorText: _captchaError),
          if (_formError != null) ...[
            const SizedBox(height: Space.l),
            Semantics(
              liveRegion: true,
              child: Text(_formError!, style: AppType.bodySmall.copyWith(color: AppColors.danger)),
            ),
          ],
          const SizedBox(height: Space.xl),
          Text.rich(
            TextSpan(
              style: AppType.caption,
              children: [
                const TextSpan(text: 'By creating an account you agree to the '),
                WidgetSpan(child: _InlineLink('Terms', () => context.push('/terms'))),
                const TextSpan(text: ', the '),
                WidgetSpan(child: _InlineLink('Reward rules', () => context.push('/rules'))),
                const TextSpan(text: ' and the '),
                WidgetSpan(child: _InlineLink('Privacy notice', () => context.push('/privacy'))),
                const TextSpan(text: '. Joining is free.'),
              ],
            ),
          ),
          const SizedBox(height: Space.xl),
          PrimaryButton(label: 'Create account', loading: _busy, onPressed: open ? _submit : null),
          const SizedBox(height: Space.l),
          Wrap(
            alignment: WrapAlignment.center,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              const Text('Already registered?', style: AppType.bodySmall),
              LinkButton(label: 'Log in', onPressed: () => context.go('/login')),
            ],
          ),
        ],
      ),
    );
  }
}

class _InlineLink extends StatelessWidget {
  const _InlineLink(this.label, this.onTap);

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    link: true,
    child: InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Text(
          label,
          style: AppType.caption.copyWith(color: AppColors.goldBright, decoration: TextDecoration.underline),
        ),
      ),
    ),
  );
}
