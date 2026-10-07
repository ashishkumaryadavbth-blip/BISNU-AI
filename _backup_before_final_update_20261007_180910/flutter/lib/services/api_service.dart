import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

class ApiService {
  ApiService({http.Client? client}) : _client = client ?? http.Client();

  static const String _configuredBaseUrl =
      String.fromEnvironment('BISNU_API_URL');

  static const FlutterSecureStorage _storage = FlutterSecureStorage();

  final http.Client _client;

  String _accountId(String username) {
    const suffix = '#bisnu-x.com';
    final normalized = username.trim().toLowerCase();
    return normalized.endsWith(suffix) ? normalized : '$normalized$suffix';
  }

  String get baseUrl {
    if (_configuredBaseUrl.isEmpty) {
      throw const ApiException(
        'BISNU_API_URL is not configured.',
      );
    }

    final configured = Uri.tryParse(_configuredBaseUrl);

    if (configured == null ||
        !configured.hasAuthority ||
        configured.host.isEmpty ||
        !{'http', 'https'}.contains(configured.scheme)) {
      throw const ApiException(
        'BISNU_API_URL is not a valid absolute URL.',
      );
    }

    if (configured.scheme != 'https' &&
        !(kDebugMode && configured.scheme == 'http')) {
      throw const ApiException(
        'BISNU-X requires HTTPS except for local debug builds.',
      );
    }

    return _configuredBaseUrl.endsWith('/')
        ? _configuredBaseUrl.substring(
            0,
            _configuredBaseUrl.length - 1,
          )
        : _configuredBaseUrl;
  }

  Future<String?> get token => _storage.read(key: 'bisnu_access_token');

  Uri _uri(
    String path, [
    Map<String, String>? query,
  ]) {
    return Uri.parse('$baseUrl$path').replace(
      queryParameters: query,
    );
  }

  Future<Map<String, dynamic>> _jsonRequest(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? query,
    bool authenticated = false,
  }) async {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };

    if (authenticated) {
      final currentToken = await token;

      if (currentToken == null || currentToken.isEmpty) {
        throw const ApiException(
          'Sign in to continue.',
        );
      }

      headers['Authorization'] = 'Bearer $currentToken';
    }

    final request = http.Request(
      method,
      _uri(path, query),
    );

    request.headers.addAll(headers);

    if (body != null) {
      request.body = jsonEncode(body);
    }

    late http.Response response;

    try {
      final streamed =
          await _client.send(request).timeout(const Duration(seconds: 45));

      response = await http.Response.fromStream(streamed);
    } on Exception catch (e) {
      throw ApiException(
        'Unable to reach BISNU-X server: $e',
      );
    }

    Map<String, dynamic> decoded = {};

    if (response.body.trim().isNotEmpty) {
      try {
        final value = jsonDecode(response.body);

        if (value is Map<String, dynamic>) {
          decoded = value;
        }
      } catch (_) {
        throw ApiException(
          'Server returned an invalid response '
          '(${response.statusCode}).',
        );
      }
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      if (response.statusCode == 401) {
        throw const ApiException(
          'Session expired. Please sign in again.',
        );
      }

      throw ApiException(
        decoded['detail']?.toString() ??
            decoded['message']?.toString() ??
            'Request failed (${response.statusCode}).',
      );
    }

    return decoded;
  }

  // ==========================================================
  // AUTH
  // ==========================================================

  Future<Map<String, dynamic>> _authenticate(
    String path,
    String username,
    String password,
  ) async {
    final result = await _jsonRequest(
      'POST',
      path,
      body: {
        'username': _accountId(username),
        'password': password,
      },
    );
    final sessionToken = result['token']?.toString();
    if (sessionToken == null || sessionToken.isEmpty) {
      throw const ApiException(
        'BISNU-X server did not return a session token.',
      );
    }
    await _storage.write(
      key: 'bisnu_access_token',
      value: sessionToken,
    );
    return result;
  }

  Future<Map<String, dynamic>> register(
    String username,
    String password,
  ) =>
      _authenticate('/v1/auth/register', username, password);

  Future<Map<String, dynamic>> login(
    String username,
    String password,
  ) =>
      _authenticate('/v1/auth/login', username, password);

  Future<Map<String, dynamic>> setCredentials(
    String username,
    String password,
  ) {
    return _jsonRequest(
      'PUT',
      '/v1/auth/credentials',
      authenticated: true,
      body: {
        'username': _accountId(username),
        'password': password,
      },
    );
  }

  Future<Map<String, dynamic>> getProfile() async {
    final result = await _jsonRequest(
      'GET',
      '/v1/auth/me',
      authenticated: true,
    );

    final rawUser = result['user'];

    if (rawUser is! Map) {
      throw const ApiException(
        'Invalid user profile returned by server.',
      );
    }

    final profile = Map<String, dynamic>.from(rawUser);

    profile['username'] ??= profile['email']?.toString().split('@').first ?? '';

    profile['phone'] ??= '';

    return profile;
  }

  Future<Map<String, dynamic>> createProfile(
    String name,
    String username,
  ) async {
    final result = await _jsonRequest(
      'PATCH',
      '/v1/auth/profile',
      authenticated: true,
      body: {
        'name': name.trim(),
        'username': _accountId(username),
      },
    );

    final profile = result['profile'];

    if (profile is! Map) {
      throw const ApiException(
        'Invalid profile returned by server.',
      );
    }

    return Map<String, dynamic>.from(profile);
  }

  Future<void> signOut() async {
    try {
      await _jsonRequest(
        'POST',
        '/v1/auth/logout',
        authenticated: true,
      );
    } catch (_) {
      // Local logout continues even if server is unavailable.
    }

    await _storage.delete(
      key: 'bisnu_access_token',
    );
  }

  // ==========================================================
  // HEALTH
  // ==========================================================

  Future<Map<String, dynamic>> getHealth() {
    return _jsonRequest(
      'GET',
      '/health',
    );
  }

  Future<Map<String, dynamic>> getStatus() {
    return _jsonRequest(
      'GET',
      '/api/status',
    );
  }

  // ==========================================================
  // MEMORY
  // ==========================================================

  Future<List<Map<String, dynamic>>> memories({
    String? query,
  }) async {
    final result = await _jsonRequest(
      'GET',
      '/v1/memory',
      query: query == null || query.trim().isEmpty
          ? null
          : {
              'query': query.trim(),
            },
      authenticated: true,
    );

    final rawItems = result['items'];

    if (rawItems is! List) {
      return [];
    }

    return rawItems
        .whereType<Map>()
        .map(
          (item) => Map<String, dynamic>.from(item),
        )
        .toList();
  }

  Future<void> addMemory(
    String text,
  ) async {
    await _jsonRequest(
      'POST',
      '/v1/memory',
      authenticated: true,
      body: {
        'text': text.trim(),
        'approved': true,
      },
    );
  }

  Future<void> deleteMemory(
    String id,
  ) async {
    await _jsonRequest(
      'DELETE',
      '/v1/memory/${Uri.encodeComponent(id)}',
      authenticated: true,
    );
  }

  // ==========================================================
  // CONVERSATIONS
  // ==========================================================

  Future<String> createConversation([
    String title = 'New conversation',
  ]) async {
    final result = await _jsonRequest(
      'POST',
      '/v1/conversations',
      authenticated: true,
      body: {
        'title': title.trim().isEmpty ? 'New conversation' : title.trim(),
      },
    );

    final id = result['conversation_id']?.toString();

    if (id == null || id.isEmpty) {
      throw const ApiException(
        'Server did not return conversation ID.',
      );
    }

    return id;
  }

  Future<List<Map<String, dynamic>>> getConversations() async {
    final result = await _jsonRequest(
      'GET',
      '/v1/conversations',
      authenticated: true,
    );

    final raw = result['conversations'];

    if (raw is! List) {
      return [];
    }

    return raw
        .whereType<Map>()
        .map(
          (item) => Map<String, dynamic>.from(item),
        )
        .toList();
  }

  Future<Map<String, dynamic>> getConversation(
    String conversationId,
  ) {
    return _jsonRequest(
      'GET',
      '/v1/conversations/'
          '${Uri.encodeComponent(conversationId)}',
      authenticated: true,
    );
  }

  // ==========================================================
  // CHAT
  // ==========================================================

  Future<String> chat({
    required List<Map<String, String>> messages,
    required String conversationId,
    required bool memoryEnabled,
    required String mode,
    required void Function(
      Map<String, dynamic> meta,
    )? onMeta,
    required void Function(
      String answer,
    ) onAnswer,
  }) async {
    final lastUserMessage = messages.lastWhere(
      (message) => message['role'] == 'user',
      orElse: () => const <String, String>{},
    );

    final prompt = lastUserMessage['content']?.trim() ?? '';

    if (prompt.isEmpty) {
      throw const ApiException(
        'Enter a message before sending.',
      );
    }

    final normalizedMode = mode.trim().toLowerCase();

    String requestedModel = 'auto';
    bool useSearch = false;

    if (normalizedMode == 'qwen') {
      requestedModel = 'qwen';
    } else if (normalizedMode == 'llama') {
      requestedModel = 'llama';
    } else if (normalizedMode == 'bisnu' || normalizedMode == 'bisnu-1.1') {
      requestedModel = 'bisnu-1.1';
    } else if (normalizedMode == 'research') {
      requestedModel = 'auto';
      useSearch = true;
    }

    final result = await _jsonRequest(
      'POST',
      '/v1/chat',
      authenticated: true,
      body: {
        'message': prompt,
        if (conversationId.isNotEmpty) 'conversation_id': conversationId,
        'model': requestedModel,
        'use_search': useSearch,
        'memory_enabled': memoryEnabled,
        'max_new_tokens': 512,
      },
    );

    onMeta?.call(result);

    final answer = result['answer']?.toString() ?? '';

    if (answer.trim().isEmpty) {
      throw const ApiException(
        'The model returned an empty response.',
      );
    }

    onAnswer(answer);

    return answer;
  }

  // ==========================================================
  // OTHER FEATURES
  // ==========================================================

  Future<void> checkScannerAccess() async {
    final result = await _jsonRequest(
      'GET',
      '/v1/scanner/access',
      authenticated: true,
    );
    if (result['allowed'] != true) {
      throw ApiException(
        result['detail']?.toString() ??
            'Scanner access requires an active Premium subscription.',
      );
    }
  }

  Future<Map<String, dynamic>> createSubscription(
    String plan,
  ) {
    return _jsonRequest(
      'POST',
      '/v1/subscriptions',
      authenticated: true,
      body: {
        'plan': plan,
      },
    );
  }

  Future<Map<String, dynamic>> getSubscription() {
    return _jsonRequest(
      'GET',
      '/v1/me/subscription',
      authenticated: true,
    );
  }

  Future<void> cancelSubscription() async {
    await _jsonRequest(
      'POST',
      '/v1/subscriptions/cancel',
      authenticated: true,
    );
  }
}

class ApiException implements Exception {
  const ApiException(this.message);

  final String message;

  @override
  String toString() => message;
}
