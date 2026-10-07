import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/chat_message.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/animated_background.dart';
import '../widgets/brand_mark.dart';
import '../widgets/glass_card.dart';
import 'voice_screen.dart';
import 'scanner_screen.dart';
import 'subscription_screen.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.api,
    required this.profile,
    required this.themeMode,
    required this.accent,
    required this.onThemeChanged,
    required this.onAccentChanged,
    required this.onSignOut,
  });

  final ApiService api;
  final Map<String, dynamic> profile;
  final ThemeMode themeMode;
  final Color accent;
  final ValueChanged<ThemeMode> onThemeChanged;
  final ValueChanged<Color> onAccentChanged;
  final VoidCallback onSignOut;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final _focus = FocusNode();
  final List<ChatMessage> _messages = [];
  final Set<String> _modes = {
    'Auto',
    'Reasoning',
    'Coding',
    'Math',
    'Science',
    'Research',
    'Hindi',
    'English',
    'Hinglish',
    'Document',
    'Creative'
  };
  String _mode = 'Auto';
  String _conversationId = '';
  List<Map<String, dynamic>> _sources = [];
  bool _memoryEnabled = true;
  bool _busy = false;
  bool _restoringHistory = false;
  late ThemeMode _themeMode;
  late Color _accent;

  String get _apiMode => _mode.toLowerCase();

  @override
  void initState() {
    super.initState();
    _themeMode = widget.themeMode;
    _accent = widget.accent;
    _loadMemoryPreference();
    _restoreLatestConversation();
  }

  Future<void> _restoreLatestConversation() async {
    if (mounted) setState(() => _restoringHistory = true);
    try {
      final conversations = await widget.api.getConversations();
      if (conversations.isNotEmpty) {
        await _loadConversation(conversations.first);
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not restore chat history: $error')),
        );
      }
    } finally {
      if (mounted) setState(() => _restoringHistory = false);
    }
  }

  Future<void> _loadConversation(
    Map<String, dynamic> conversation,
  ) async {
    final id = conversation['id']?.toString() ?? '';
    if (id.isEmpty) return;
    final response = await widget.api.getConversation(id);
    final rawMessages = response['messages'];
    final restored = rawMessages is List
        ? rawMessages.whereType<Map>().map((message) {
            return ChatMessage(
              role: message['role']?.toString() ?? 'user',
              content: message['content']?.toString() ?? '',
            );
          }).toList()
        : <ChatMessage>[];
    if (!mounted) return;
    setState(() {
      _conversationId = id;
      _messages
        ..clear()
        ..addAll(restored);
      _sources = [];
    });
    _scrollToEnd();
  }

  Future<void> _showConversationHistory() async {
    try {
      final conversations = await widget.api.getConversations();
      if (!mounted) return;
      if (conversations.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No saved conversations yet.')),
        );
        return;
      }
      await showModalBottomSheet<void>(
        context: context,
        showDragHandle: true,
        builder: (context) => SafeArea(
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            children: [
              Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  'Saved conversations',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              for (final conversation in conversations)
                ListTile(
                  leading: const Icon(Icons.forum_outlined),
                  title: Text(
                    conversation['title']?.toString() ?? 'Conversation',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  selected: conversation['id']?.toString() == _conversationId,
                  onTap: () async {
                    Navigator.pop(context);
                    setState(() => _restoringHistory = true);
                    try {
                      await _loadConversation(conversation);
                    } catch (error) {
                      if (mounted) {
                        ScaffoldMessenger.of(this.context).showSnackBar(
                          SnackBar(
                            content:
                                Text('Could not load conversation: $error'),
                          ),
                        );
                      }
                    } finally {
                      if (mounted) {
                        setState(() => _restoringHistory = false);
                      }
                    }
                  },
                ),
            ],
          ),
        ),
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not load chat history: $error')),
        );
      }
    }
  }

  Future<void> _updateLoginCredentials() async {
    const accountSuffix = '#bisnu-x.com';
    final savedAccountId = widget.profile['username']?.toString() ?? '';
    final username = TextEditingController(
      text: savedAccountId.endsWith(accountSuffix)
          ? savedAccountId.substring(
              0, savedAccountId.length - accountSuffix.length)
          : savedAccountId,
    );
    final password = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Set login credentials'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: username,
              autocorrect: false,
              textCapitalization: TextCapitalization.none,
              decoration: const InputDecoration(
                labelText: 'BISNU-X username',
                suffixText: '#bisnu-x.com',
              ),
            ),
            TextField(
              controller: password,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: 'New password (10+ characters)',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      try {
        final result = await widget.api.setCredentials(
          username.text,
          password.text,
        );
        final account = result['user'];
        if (account is Map) {
          widget.profile['username'] = account['username'];
        }
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Login credentials saved.')),
          );
        }
      } catch (error) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Could not save credentials: $error')),
          );
        }
      }
    }
    username.dispose();
    password.dispose();
  }

  Future<void> _loadMemoryPreference() async {
    final prefs = await SharedPreferences.getInstance();
    if (mounted)
      setState(() => _memoryEnabled = prefs.getBool('memory_enabled') ?? true);
  }

  Future<void> _setMemory(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('memory_enabled', enabled);
    if (mounted) setState(() => _memoryEnabled = enabled);
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients)
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 220), curve: Curves.easeOut);
    });
  }

  Future<String> _sendText([String? voiceText]) async {
    final text = (voiceText ?? _input.text).trim();
    if (text.isEmpty || _busy || _restoringHistory) return '';
    _focus.unfocus();
    _input.clear();
    final userMessage = ChatMessage(role: 'user', content: text);
    final assistantMessage = ChatMessage(role: 'assistant', content: '');
    setState(() {
      _messages.add(userMessage);
      _messages.add(assistantMessage);
      _sources = [];
      _busy = true;
    });
    _scrollToEnd();
    try {
      final prior =
          _messages.where((message) => message.content.isNotEmpty).toList();
      final answer = await widget.api.chat(
        messages: prior
            .map(
                (message) => {'role': message.role, 'content': message.content})
            .toList(),
        conversationId: _conversationId,
        memoryEnabled: _memoryEnabled,
        mode: _apiMode,
        onMeta: (meta) {
          if (!mounted) return;
          setState(() {
            _conversationId =
                meta['conversation_id']?.toString() ?? _conversationId;
            _sources = (meta['sources'] as List<dynamic>? ?? const [])
                .cast<Map<String, dynamic>>();
          });
        },
        onAnswer: (answer) {
          assistantMessage.content = answer;
          if (mounted) setState(() {});
          _scrollToEnd();
        },
      );
      return answer;
    } catch (error) {
      assistantMessage.content = 'Request failed: $error';
      if (mounted) setState(() {});
      return '';
    } finally {
      if (mounted) setState(() => _busy = false);
      _scrollToEnd();
    }
  }

  Future<void> _startVoice() async {
    await Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => VoiceScreen(onPrompt: _sendText)));
  }

  Future<void> _openScanner() async {
    await Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => ScannerScreen(
        api: widget.api,
        onUseText: (text) {
          _input.text = text;
          _sendText();
        },
      ),
    ));
  }

  Future<void> _openSubscriptions() async {
    await Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => SubscriptionScreen(api: widget.api),
    ));
  }

  Future<void> _showMemory() async {
    final search = TextEditingController();
    final input = TextEditingController();
    List<Map<String, dynamic>> items = [];
    String? error;
    try {
      items = await widget.api.memories();
    } catch (exception) {
      error = exception.toString();
    }
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (sheetContext) => StatefulBuilder(builder: (context, update) {
        final term = search.text.toLowerCase();
        final filtered = items
            .where(
                (item) => item['text'].toString().toLowerCase().contains(term))
            .toList();
        return Padding(
          padding: EdgeInsets.only(
              left: 20,
              right: 20,
              top: 8,
              bottom: MediaQuery.of(context).viewInsets.bottom + 20),
          child: SizedBox(
            height: MediaQuery.of(context).size.height * 0.78,
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Saved memory',
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 8),
              SwitchListTile.adaptive(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Use memory in chat'),
                  value: _memoryEnabled,
                  onChanged: (value) async {
                    await _setMemory(value);
                    update(() {});
                  }),
              Row(children: [
                Expanded(
                    child: TextField(
                        controller: input,
                        maxLength: 4000,
                        decoration: const InputDecoration(
                            hintText: 'Save an approved detail'))),
                IconButton.filled(
                    onPressed: () async {
                      try {
                        await widget.api.addMemory(input.text.trim());
                        input.clear();
                        items = await widget.api.memories();
                        update(() {});
                      } catch (exception) {
                        update(() => error = exception.toString());
                      }
                    },
                    icon: const Icon(Icons.add_rounded)),
              ]),
              TextField(
                  controller: search,
                  onChanged: (_) => update(() {}),
                  decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.search_rounded),
                      hintText: 'Search memories')),
              if (error != null)
                Padding(
                    padding: const EdgeInsets.all(8),
                    child: Text(error!,
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.error))),
              const SizedBox(height: 10),
              Expanded(
                  child: filtered.isEmpty
                      ? Center(
                          child: Text(
                              items.isEmpty
                                  ? 'No saved memories'
                                  : 'No matches',
                              style: TextStyle(
                                  color: Theme.of(context).hintColor)))
                      : ListView.builder(
                          itemCount: filtered.length,
                          itemBuilder: (_, index) {
                            final item = filtered[index];
                            return ListTile(
                              contentPadding: EdgeInsets.zero,
                              title: Text(item['text'].toString()),
                              subtitle: Text(item['created_at']
                                  .toString()
                                  .split('T')
                                  .first),
                              trailing: IconButton(
                                  tooltip: 'Delete memory',
                                  icon:
                                      const Icon(Icons.delete_outline_rounded),
                                  onPressed: () async {
                                    await widget.api
                                        .deleteMemory(item['id'].toString());
                                    items.removeWhere(
                                        (entry) => entry['id'] == item['id']);
                                    update(() {});
                                  }),
                            );
                          },
                        )),
            ]),
          ),
        );
      }),
    );
    search.dispose();
    input.dispose();
  }

  Future<void> _showSettings() async {
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
          child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Settings',
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 12),
              ListTile(
                leading: CircleAvatar(
                    backgroundColor: Theme.of(context)
                        .colorScheme
                        .primary
                        .withValues(alpha: 0.16),
                    child: Text((widget.profile['name'] as String? ?? '?')
                        .characters
                        .first
                        .toUpperCase())),
                title:
                    Text(widget.profile['name']?.toString() ?? 'BISNU-X user'),
                subtitle: Text(
                    '${widget.profile['username'] ?? ''} · ${widget.profile['phone'] ?? ''}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis),
              ),
              if (widget.profile['created_at'] != null)
                ListTile(
                    leading: const Icon(Icons.calendar_today_rounded),
                    title: const Text('Member since'),
                    subtitle: Text(widget.profile['created_at']
                        .toString()
                        .split('T')
                        .first)),
              ListTile(
                  leading: const Icon(Icons.forum_outlined),
                  title: const Text('Messages in this conversation'),
                  trailing: Text('${_messages.length}')),
              ListTile(
                leading: const Icon(Icons.key_outlined),
                title: const Text('Set login credentials'),
                subtitle: const Text(
                  'Save a username and password for future sign-ins',
                ),
                onTap: () {
                  Navigator.pop(context);
                  _updateLoginCredentials();
                },
              ),
              SwitchListTile.adaptive(
                  title: const Text('Dark appearance'),
                  value: _themeMode == ThemeMode.dark,
                  onChanged: (value) {
                    final mode = value ? ThemeMode.dark : ThemeMode.light;
                    setState(() => _themeMode = mode);
                    widget.onThemeChanged(mode);
                  }),
              ListTile(
                  title: const Text('Accent color'),
                  subtitle: const Text('Cyan · Blue · Violet · Emerald · Gold'),
                  trailing: Wrap(
                      spacing: 4,
                      children: [
                        AppTheme.cyan,
                        AppTheme.blue,
                        AppTheme.violet,
                        AppTheme.emerald,
                        AppTheme.gold,
                      ]
                          .map((color) => GestureDetector(
                                onTap: () {
                                  setState(() => _accent = color);
                                  widget.onAccentChanged(color);
                                },
                                child: Container(
                                    width: 24,
                                    height: 24,
                                    decoration: BoxDecoration(
                                        color: color,
                                        shape: BoxShape.circle,
                                        border: Border.all(
                                            color: _accent == color
                                                ? Colors.white
                                                : Colors.transparent,
                                            width: 2))),
                              ))
                          .toList())),
              ListTile(
                  leading: const Icon(Icons.info_outline_rounded),
                  title: const Text('About BISNU-X.1'),
                  subtitle: const Text(
                      'Local-first AI client. Responses depend on your configured model.')),
              ListTile(
                  leading: const Icon(Icons.logout_rounded),
                  title: const Text('Sign out'),
                  onTap: () {
                    Navigator.pop(context);
                    widget.onSignOut();
                  }),
            ]),
      )),
    );
  }

  void _newChat() {
    setState(() {
      _messages.clear();
      _sources.clear();
      _conversationId = '';
    });
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final greeting =
        (widget.profile['name'] as String? ?? 'there').split(' ').first;
    return Scaffold(
      appBar: AppBar(
        leadingWidth: 62,
        leading: const Padding(
            padding: EdgeInsets.only(left: 16),
            child: Center(child: BrandMark(size: 36, compact: true))),
        title: const BrandMark(size: 29),
        actions: [
          IconButton(
              tooltip: 'Saved conversations',
              onPressed: _showConversationHistory,
              icon: const Icon(Icons.history_rounded)),
          IconButton(
              tooltip: 'Subscriptions',
              onPressed: _openSubscriptions,
              icon: const Icon(Icons.workspace_premium_outlined)),
          IconButton(
              tooltip: 'Scan document',
              onPressed: _openScanner,
              icon: const Icon(Icons.document_scanner_outlined)),
          IconButton(
              tooltip: 'Voice conversation',
              onPressed: _startVoice,
              icon: const Icon(Icons.graphic_eq_rounded)),
          PopupMenuButton<String>(
            tooltip: 'Profile and settings',
            onSelected: (value) {
              if (value == 'memory') _showMemory();
              if (value == 'subscriptions') _openSubscriptions();
              if (value == 'settings') _showSettings();
            },
            itemBuilder: (_) => const [
              PopupMenuItem(
                  value: 'memory',
                  child: ListTile(
                      leading: Icon(Icons.psychology_alt_outlined),
                      title: Text('Memory'))),
              PopupMenuItem(
                  value: 'subscriptions',
                  child: ListTile(
                      leading: Icon(Icons.workspace_premium_outlined),
                      title: Text('Subscriptions'))),
              PopupMenuItem(
                  value: 'settings',
                  child: ListTile(
                      leading: Icon(Icons.tune_rounded),
                      title: Text('Settings'))),
            ],
            child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: CircleAvatar(
                    radius: 16,
                    backgroundColor: Theme.of(context)
                        .colorScheme
                        .primary
                        .withValues(alpha: 0.18),
                    child: Text(greeting.characters.first.toUpperCase(),
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.primary)))),
          ),
        ],
      ),
      body: AnimatedBackground(
        child: Column(children: [
          if (_restoringHistory) const LinearProgressIndicator(minHeight: 2),
          Expanded(
            child: _messages.isEmpty
                ? _Welcome(
                    greeting: greeting,
                    onPrompt: (prompt) {
                      _input.text = prompt;
                      _sendText();
                    })
                : ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 26),
                    itemCount: _messages.length + (_sources.isNotEmpty ? 1 : 0),
                    itemBuilder: (context, index) {
                      if (index >= _messages.length)
                        return _SourceStrip(sources: _sources);
                      return _MessageBubble(
                          message: _messages[index],
                          onCopy: () {
                            Clipboard.setData(
                                ClipboardData(text: _messages[index].content));
                            ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('Copied')));
                          });
                    },
                  ),
          ),
          SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
                child: Column(children: [
                  Row(children: [
                    Expanded(
                        child: DropdownButtonFormField<String>(
                      initialValue: _mode,
                      decoration: const InputDecoration(
                          isDense: true,
                          prefixIcon:
                              Icon(Icons.auto_awesome_rounded, size: 18),
                          contentPadding: EdgeInsets.symmetric(
                              horizontal: 12, vertical: 8)),
                      items: _modes
                          .map((mode) =>
                              DropdownMenuItem(value: mode, child: Text(mode)))
                          .toList(),
                      onChanged: _busy
                          ? null
                          : (mode) => setState(() => _mode = mode ?? 'Auto'),
                    )),
                    const SizedBox(width: 8),
                    IconButton(
                        tooltip: _memoryEnabled ? 'Memory on' : 'Memory off',
                        onPressed: () => _setMemory(!_memoryEnabled),
                        icon: Icon(
                            _memoryEnabled
                                ? Icons.psychology_alt_rounded
                                : Icons.psychology_alt_outlined,
                            color: _memoryEnabled
                                ? Theme.of(context).colorScheme.primary
                                : null)),
                    IconButton(
                        tooltip: 'New conversation',
                        onPressed: _newChat,
                        icon: const Icon(Icons.add_comment_outlined)),
                  ]),
                  const SizedBox(height: 8),
                  GlassCard(
                      padding: const EdgeInsets.fromLTRB(14, 7, 8, 7),
                      radius: 21,
                      child: Row(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Expanded(
                                child: TextField(
                                    controller: _input,
                                    focusNode: _focus,
                                    minLines: 1,
                                    maxLines: 6,
                                    textCapitalization:
                                        TextCapitalization.sentences,
                                    decoration: const InputDecoration(
                                        hintText: 'Message BISNU-X.1',
                                        border: InputBorder.none,
                                        filled: false),
                                    onSubmitted: (_) => _sendText())),
                            IconButton(
                                tooltip: 'Voice input',
                                onPressed: _busy || _restoringHistory
                                    ? null
                                    : _startVoice,
                                icon: const Icon(Icons.mic_none_rounded)),
                            IconButton.filled(
                                tooltip: _busy ? 'Generating' : 'Send',
                                onPressed: _busy || _restoringHistory
                                    ? null
                                    : () => _sendText(),
                                icon: _busy
                                    ? const SizedBox.square(
                                        dimension: 19,
                                        child: CircularProgressIndicator(
                                            strokeWidth: 2))
                                    : const Icon(Icons.arrow_upward_rounded)),
                          ])),
                  const SizedBox(height: 6),
                  Text(
                      'Responses come from your configured BISNU-X model. Verify important information.',
                      style: Theme.of(context)
                          .textTheme
                          .labelSmall
                          ?.copyWith(color: Theme.of(context).hintColor),
                      textAlign: TextAlign.center),
                ]),
              )),
        ]),
      ),
    );
  }
}

class _Welcome extends StatelessWidget {
  const _Welcome({required this.greeting, required this.onPrompt});
  final String greeting;
  final ValueChanged<String> onPrompt;

  @override
  Widget build(BuildContext context) => Center(
      child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 540),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const BrandMark(size: 48),
              const SizedBox(height: 32),
              Text('Your workspace',
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      color: Theme.of(context).colorScheme.primary,
                      letterSpacing: 1.5)),
              const SizedBox(height: 7),
              Text('What are we working on, $greeting?',
                  style: Theme.of(context)
                      .textTheme
                      .headlineMedium
                      ?.copyWith(fontWeight: FontWeight.w700)),
              const SizedBox(height: 22),
              for (final prompt in [
                'Explain a difficult idea in simple terms',
                'Help me debug this code',
                'Research the latest developments'
              ])
                Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: InkWell(
                        onTap: () => onPrompt(prompt),
                        borderRadius: BorderRadius.circular(16),
                        child: GlassCard(
                            child: Row(children: [
                          Icon(Icons.arrow_outward_rounded,
                              color: Theme.of(context).colorScheme.primary),
                          const SizedBox(width: 14),
                          Expanded(child: Text(prompt)),
                          const Icon(Icons.chevron_right_rounded)
                        ])))),
            ]),
          )));
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message, required this.onCopy});
  final ChatMessage message;
  final VoidCallback onCopy;

  @override
  Widget build(BuildContext context) {
    if (message.isUser) {
      return Align(
          alignment: Alignment.centerRight,
          child: Container(
            constraints: const BoxConstraints(maxWidth: 340),
            margin: const EdgeInsets.only(bottom: 16, left: 36),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
                color: Theme.of(context)
                    .colorScheme
                    .primary
                    .withValues(alpha: 0.16),
                borderRadius: BorderRadius.circular(18)),
            child: Text(message.content),
          ));
    }
    return Padding(
        padding: const EdgeInsets.only(bottom: 22, right: 8),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const BrandMark(size: 25, compact: true),
            const SizedBox(width: 9),
            Text('BISNU-X.1',
                style: Theme.of(context)
                    .textTheme
                    .labelMedium
                    ?.copyWith(color: Theme.of(context).colorScheme.primary)),
            const Spacer(),
            IconButton(
                tooltip: 'Copy response',
                onPressed: message.content.isEmpty ? null : onCopy,
                icon: const Icon(Icons.copy_rounded, size: 17))
          ]),
          const SizedBox(height: 4),
          message.content.isEmpty
              ? const _ThinkingIndicator()
              : MarkdownBody(
                  data: message.content,
                  selectable: true,
                  styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context))
                      .copyWith(
                          p: Theme.of(context)
                              .textTheme
                              .bodyLarge
                              ?.copyWith(height: 1.55))),
          Text(
              '${message.createdAt.hour.toString().padLeft(2, '0')}:${message.createdAt.minute.toString().padLeft(2, '0')}',
              style: Theme.of(context)
                  .textTheme
                  .labelSmall
                  ?.copyWith(color: Theme.of(context).hintColor)),
        ]));
  }
}

class _ThinkingIndicator extends StatefulWidget {
  const _ThinkingIndicator();
  @override
  State<_ThinkingIndicator> createState() => _ThinkingIndicatorState();
}

class _ThinkingIndicatorState extends State<_ThinkingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 850))
    ..repeat(reverse: true);
  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: _controller,
        builder: (context, _) => Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(
            3,
            (index) => Padding(
              padding: const EdgeInsets.only(right: 5),
              child: Transform.translate(
                offset: Offset(0,
                    -math.sin((_controller.value + index / 3) * math.pi) * 4),
                child: CircleAvatar(
                  radius: 3,
                  backgroundColor: Theme.of(context)
                      .colorScheme
                      .primary
                      .withValues(alpha: 0.45 + _controller.value * 0.5),
                ),
              ),
            ),
          ),
        ),
      );
}

class _SourceStrip extends StatelessWidget {
  const _SourceStrip({required this.sources});
  final List<Map<String, dynamic>> sources;
  @override
  Widget build(BuildContext context) => SizedBox(
        height: 86,
        child: ListView(
          scrollDirection: Axis.horizontal,
          children: sources
              .map((source) => Padding(
                    padding: const EdgeInsets.only(right: 9),
                    child: SizedBox(
                      width: 230,
                      child: GlassCard(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                source['title']?.toString() ?? 'Source',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: Theme.of(context).textTheme.labelLarge,
                              ),
                              const Spacer(),
                              Text(
                                '${source['domain'] ?? source['freshness'] ?? 'Retrieved source'}',
                                style: Theme.of(context)
                                    .textTheme
                                    .labelSmall
                                    ?.copyWith(
                                        color: Theme.of(context)
                                            .colorScheme
                                            .primary),
                              ),
                            ]),
                      ),
                    ),
                  ))
              .toList(),
        ),
      );
}
