import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/api_service.dart';

class SubscriptionScreen extends StatefulWidget {
  const SubscriptionScreen({super.key, required this.api});

  final ApiService api;

  @override
  State<SubscriptionScreen> createState() => _SubscriptionScreenState();
}

class _SubscriptionScreenState extends State<SubscriptionScreen> {
  Map<String, dynamic>? _subscription;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await widget.api.getSubscription();
      if (mounted) setState(() => _subscription = result);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _start(String plan) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await widget.api.createSubscription(plan);
      final checkout = Uri.parse(result['checkout_url'].toString());
      if (checkout.scheme != 'https' ||
          !await launchUrl(checkout, mode: LaunchMode.externalApplication)) {
        throw const ApiException('Could not open Razorpay checkout.');
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Checkout opened. Access activates only after Razorpay confirms '
              'the subscription to the server.',
            ),
          ),
        );
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _cancel() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Cancel renewal?'),
        content: const Text(
          'Razorpay will schedule cancellation at the end of the current cycle. '
          'Current access remains governed by the verified subscription period.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Keep plan'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Cancel renewal'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.api.cancelSubscription();
      await _refresh();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final current = _subscription?['plan']?.toString() ?? 'FREE';
    final providerStatus =
        (_subscription?['subscription'] as Map<String, dynamic>?)?['status']
            ?.toString();
    final paymentsAvailable = _subscription?['available'] == true;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Subscriptions'),
        actions: [
          IconButton(
            tooltip: 'Refresh payment status',
            onPressed: _busy ? null : _refresh,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Card(
              child: ListTile(
                leading: const Icon(Icons.verified_user_outlined),
                title: Text('Current plan: $current'),
                subtitle: Text(
                  providerStatus == null
                      ? 'No active Razorpay subscription'
                      : 'Razorpay status: $providerStatus',
                ),
              ),
            ),
            const SizedBox(height: 16),
            for (final plan in const ['PREMIUM', 'ULTRA'])
              Card(
                child: ListTile(
                  title: Text(plan),
                  subtitle: Text(
                    paymentsAvailable
                        ? 'Monthly recurring plan. Final amount and billing terms '
                            'are shown on Razorpay-hosted checkout.'
                        : 'Coming Soon',
                  ),
                  trailing: FilledButton(
                    onPressed: !paymentsAvailable ||
                            _busy ||
                            current == plan
                        ? null
                        : () => _start(plan),
                    child: Text(
                      !paymentsAvailable
                          ? 'Coming Soon'
                          : current == plan
                              ? 'Active'
                              : 'Subscribe',
                    ),
                  ),
                ),
              ),
            if (providerStatus == 'active')
              OutlinedButton.icon(
                onPressed: _busy ? null : _cancel,
                icon: const Icon(Icons.cancel_outlined),
                label: const Text('Cancel renewal'),
              ),
            if (_busy) ...[
              const SizedBox(height: 16),
              const Center(child: CircularProgressIndicator()),
            ],
            if (_error case final error?) ...[
              const SizedBox(height: 12),
              SelectableText(
                error,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
            const SizedBox(height: 12),
            Text(
              paymentsAvailable
                  ? 'BISNU-X never activates a paid plan from a browser callback. '
                      'The backend requires a valid Razorpay webhook signature '
                      'and a subscription created by this server.'
                  : 'Paid plans and Premium scanner access will be available '
                      'after Razorpay is configured. Payment credentials alone '
                      'do not activate a plan; a verified payment is required.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}
