import 'package:flutter/material.dart';

import '../../app/theme/spacing.dart';
import '../api/models.dart';
import 'buttons.dart';
import 'state_views.dart';

/// Loads a server-paginated list page by page ("Load more"), never all at once.
class PagedList<T> extends StatefulWidget {
  const PagedList({
    super.key,
    required this.load,
    required this.itemBuilder,
    required this.emptyTitle,
    required this.emptyMessage,
    this.header = const [],
  });

  final Future<Paged<T>> Function(String? cursor) load;
  final Widget Function(T item) itemBuilder;
  final String emptyTitle;
  final String emptyMessage;
  final List<Widget> header;

  @override
  State<PagedList<T>> createState() => _PagedListState<T>();
}

class _PagedListState<T> extends State<PagedList<T>> {
  final List<T> _items = [];
  String? _cursor;
  bool _done = false;
  bool _loading = false;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _next();
  }

  Future<void> _reload() async {
    setState(() {
      _items.clear();
      _cursor = null;
      _done = false;
      _error = null;
    });
    await _next();
  }

  Future<void> _next() async {
    if (_loading || _done) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await widget.load(_cursor);
      if (!mounted) return;
      setState(() {
        _items.addAll(page.items);
        _cursor = page.nextCursor;
        _done = page.nextCursor == null;
      });
    } on Object catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final children = <Widget>[...widget.header];
    if (_items.isEmpty && _loading) {
      children.add(const LoadingView());
    } else if (_items.isEmpty && _error != null) {
      children.add(ErrorView(error: _error!, onRetry: _next));
    } else if (_items.isEmpty && _done) {
      children.add(EmptyView(title: widget.emptyTitle, message: widget.emptyMessage));
    } else {
      children.addAll(_items.map(widget.itemBuilder));
      if (_error != null) {
        children.add(Padding(
          padding: const EdgeInsets.only(top: Space.l),
          child: ErrorView(error: _error!, onRetry: _next),
        ));
      } else if (!_done) {
        children.add(Padding(
          padding: const EdgeInsets.only(top: Space.l),
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : SecondaryButton(label: 'Load more', onPressed: _next),
        ));
      }
    }
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(Space.screen, Space.s, Space.screen, Space.xxxl),
        children: children,
      ),
    );
  }
}
