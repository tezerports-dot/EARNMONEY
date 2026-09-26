import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/config/config_controller.dart';
import '../core/launch/launch_gate_controller.dart';
import 'router.dart';
import 'theme/app_theme.dart';

class FutureFashionApp extends ConsumerStatefulWidget {
  const FutureFashionApp({super.key});

  @override
  ConsumerState<FutureFashionApp> createState() => _FutureFashionAppState();
}

class _FutureFashionAppState extends ConsumerState<FutureFashionApp> with WidgetsBindingObserver {
  DateTime _lastConfigLoad = DateTime.now();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Coming back to the app: refresh dates, counters and maintenance state,
    // at most once a minute.
    if (state == AppLifecycleState.resumed) {
      if (ref.read(configProvider)?.config.launchGateEnabled == true && ref.read(gatePassedProvider)) {
        ref.read(gatePassedProvider.notifier).state = false;
      }
      if (DateTime.now().difference(_lastConfigLoad) > const Duration(minutes: 1)) {
        _lastConfigLoad = DateTime.now();
        ref.read(configProvider.notifier).reload().ignore();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'Future Fashion',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.dark,
      routerConfig: router,
    );
  }
}
