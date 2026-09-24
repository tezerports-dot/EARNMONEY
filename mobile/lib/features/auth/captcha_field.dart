import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/api/future_fashion_api.dart';
import '../../core/api/models.dart';
import '../../core/providers.dart';
import '../../core/widgets/inputs.dart';
import '../../core/widgets/state_views.dart';

/// The server's arithmetic check. Each question works once, so the form
/// asks for a new one after every failed attempt.
class CaptchaController extends ChangeNotifier {
  Captcha? captcha;
  final answer = TextEditingController();
  bool loading = false;
  Object? error;

  Future<void> load(FutureFashionApi api) async {
    loading = true;
    error = null;
    answer.clear();
    notifyListeners();
    try {
      captcha = await api.captcha();
    } on Object catch (e) {
      error = e;
      captcha = null;
    }
    loading = false;
    notifyListeners();
  }

  @override
  void dispose() {
    answer.dispose();
    super.dispose();
  }
}

class CaptchaField extends ConsumerWidget {
  const CaptchaField({super.key, required this.controller, this.errorText});

  final CaptchaController controller;
  final String? errorText;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final captcha = controller.captcha;
        return Container(
          padding: const EdgeInsets.all(Space.l),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(Radii.input),
            border: Border.all(color: AppColors.line),
            color: Colors.white.withValues(alpha: 0.03),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.calculate_outlined, color: AppColors.gold, size: 20),
                  const SizedBox(width: Space.s),
                  const Expanded(child: Text('Quick check', style: AppType.label)),
                  IconButton(
                    tooltip: 'New question',
                    onPressed: controller.loading ? null : () => controller.load(ref.read(apiProvider)),
                    icon: const Icon(Icons.refresh_rounded, color: AppColors.textSecondary),
                  ),
                ],
              ),
              const SizedBox(height: Space.s),
              if (controller.loading)
                const LinearProgressIndicator()
              else if (captcha == null)
                Text(controller.error == null ? 'Loading…' : errorMessage(controller.error!), style: AppType.bodySmall)
              else
                Row(
                  children: [
                    Semantics(
                      label: 'Question: ${captcha.question.replaceAll('−', 'minus').replaceAll('+', 'plus')}',
                      excludeSemantics: true,
                      child: Text(captcha.question, style: AppType.title),
                    ),
                    const SizedBox(width: Space.l),
                    Expanded(
                      child: AppTextField(
                        controller: controller.answer,
                        label: 'Answer',
                        errorText: errorText,
                        keyboardType: TextInputType.number,
                        inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(3)],
                        textInputAction: TextInputAction.done,
                      ),
                    ),
                  ],
                ),
            ],
          ),
        );
      },
    );
  }
}
