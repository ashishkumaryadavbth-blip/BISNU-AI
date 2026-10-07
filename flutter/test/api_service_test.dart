import 'package:flutter_test/flutter_test.dart';

import '../lib/services/api_service.dart';

const _configuredApiUrl = String.fromEnvironment('BISNU_API_URL');

void main() {
  test(
    'debug builds accept the configured local HTTP backend',
    () {
      expect(_configuredApiUrl, startsWith('http://'));
      expect(ApiService().baseUrl, _configuredApiUrl);
    },
    skip: !_configuredApiUrl.startsWith('http://'),
  );
}
