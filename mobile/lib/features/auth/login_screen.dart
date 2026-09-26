import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/api/api_exception.dart';
import '../../core/auth/session_controller.dart';
import '../../core/providers.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/illustrations.dart';
import '../../core/widgets/inputs.dart';
import '../../core/widgets/screen.dart';
import '../../core/widgets/state_views.dart';
import 'captcha_field.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _phone = TextEditingController();
  final _password = TextEditingController();
  final _captcha = CaptchaController();
  bool _needsCaptcha = false;
  bool _busy = false;
  String? _phoneError;
  String? _passwordError;
  String? _captchaError;
  String? _formError;

  @override
  void dispose() {
    _phone.dispose();
    _password.dispose();
    _captcha.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    setState(() {
      _phoneError = Validators.indianMobile(_phone.text);
      _passwordError = _password.text.isEmpty ? 'Enter your password.' : null;
      _captchaError = _needsCaptcha && _captcha.answer.text.isEmpty ? 'Answer the question.' : null;
      _formError = null;
    });
    if (_phoneError != null || _passwordError != null || _captchaError != null) return;

    setState(() => _busy = true);
    try {
      await ref
          .read(sessionProvider.notifier)
          .login(
            phone: _phone.text.trim(),
            password: _password.text,
            captchaId: _needsCaptcha ? _captcha.captcha?.id : null,
            captchaAnswer: _needsCaptcha ? _captcha.answer.text : null,
          );
      // The router moves on as soon as the session changes.
    } on ServerRejection catch (e) {
      final needsCaptcha = e.code == 'CAPTCHA_REQUIRED' || e.code == 'CAPTCHA_INVALID' || _needsCaptcha;
      setState(() {
        _needsCaptcha = needsCaptcha;
        _captchaError = e.code == 'CAPTCHA_INVALID' ? e.message : null;
        _formError = switch (e.code) {
          'CAPTCHA_REQUIRED' => 'For your security, please answer the question below.',
          'CAPTCHA_INVALID' => null,
          'RATE_LIMITED' =>
            e.retryAfter == null
                ? e.message
                : 'Too many attempts. Try again in ${(e.retryAfter!.inMinutes + 1)} minutes.',
          _ => e.message,
        };
      });
      // A question works once: always fetch a fresh one after a failure.
      if (needsCaptcha) await _captcha.load(ref.read(apiProvider));
    } on ApiException catch (e) {
      setState(() => _formError = e.userMessage);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider).value;
    final notice = session is SignedOut ? session.notice : null;
    return AutofillGroup(
      child: AppScreen(
        showBack: false,
        children: [
          const SizedBox(height: Space.xxl),
          Center(child: Illustrations.shield(size: 130)),
          const SizedBox(height: Space.xxl),
          Semantics(header: true, child: const Text('Welcome back', style: AppType.headline)),
          const SizedBox(height: Space.s),
          const Text('Log in with your mobile number and password.', style: AppType.body),
          const SizedBox(height: Space.xxl),
          if (notice != null) ...[
            GlassCard(
              padding: const EdgeInsets.all(Space.l),
              child: Text(notice, style: AppType.bodySmall.copyWith(color: AppColors.warning)),
            ),
            const SizedBox(height: Space.l),
          ],
          PhoneField(controller: _phone, errorText: _phoneError),
          const FieldGap(),
          PasswordField(controller: _password, errorText: _passwordError, onSubmitted: (_) => _submit()),
          if (_needsCaptcha) ...[const FieldGap(), CaptchaField(controller: _captcha, errorText: _captchaError)],
          if (_formError != null) ...[
            const SizedBox(height: Space.l),
            Semantics(
              liveRegion: true,
              child: Text(_formError!, style: AppType.bodySmall.copyWith(color: AppColors.danger)),
            ),
          ],
          const SizedBox(height: Space.xxl),
          PrimaryButton(label: 'Log in', loading: _busy, onPressed: _submit),
          const SizedBox(height: Space.l),
          Wrap(
            alignment: WrapAlignment.center,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              const Text('New here?', style: AppType.bodySmall),
              LinkButton(label: 'Create an account', onPressed: () => context.go('/signup')),
            ],
          ),
          Center(
            child: LinkButton(
              label: 'Forgot password?',
              onPressed: () => showMessage(context, 'Contact support from the Support page to reset your password.'),
            ),
          ),
          Center(
            child: LinkButton(label: 'Support', onPressed: () => context.push('/support')),
          ),
        ],
      ),
    );
  }
}
