import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:future_fashion/core/api/models.dart';
import 'package:future_fashion/core/providers.dart';
import 'package:future_fashion/features/recruitment/recruitment_screen.dart';

import 'support/fakes.dart';

void main() {
  Widget screen(FakeApi api) => ProviderScope(
    overrides: [apiProvider.overrideWithValue(api)],
    child: const MaterialApp(home: RecruitmentScreen()),
  );

  testWidgets('shows an empty recruitment state', (tester) async {
    await tester.pumpWidget(screen(FakeApi()));
    await tester.pumpAndSettle();

    expect(find.text('No openings right now'), findsOneWidget);
    expect(find.text('Check back soon.'), findsOneWidget);
  });

  testWidgets('shows recruitment posts and their apply action', (tester) async {
    final api = FakeApi()
      ..recruitmentResponse = const [
        RecruitmentPost(
          title: 'Flutter Developer',
          location: 'Remote',
          employmentType: 'Full-time',
          description: 'Build polished mobile experiences.',
          applyUrl: 'https://example.test/apply',
          applyEmail: null,
        ),
      ];
    await tester.pumpWidget(screen(api));
    await tester.pumpAndSettle();

    expect(find.text('Flutter Developer'), findsOneWidget);
    expect(find.text('Remote • Full-time'), findsOneWidget);
    expect(find.text('Build polished mobile experiences.'), findsOneWidget);
    expect(find.text('Apply'), findsOneWidget);
  });

  testWidgets('bottom navigation exposes five destinations', (tester) async {
    final env = TestEnv(signedIn: true);
    await pumpApp(tester, env);

    expect(find.byType(NavigationDestination), findsNWidgets(5));
    expect(find.text('Jobs'), findsOneWidget);
  });
}
