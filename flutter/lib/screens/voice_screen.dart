import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

import '../widgets/voice_orb.dart';

class VoiceScreen extends StatefulWidget {
  const VoiceScreen({super.key, required this.onPrompt});

  final Future<String> Function(String prompt) onPrompt;

  @override
  State<VoiceScreen> createState() => _VoiceScreenState();
}

class _VoiceScreenState extends State<VoiceScreen> {
  final stt.SpeechToText _speech = stt.SpeechToText();
  final FlutterTts _tts = FlutterTts();
  bool _available = false;
  bool _listening = false;
  bool _speaking = false;
  bool _muted = false;
  bool _busy = false;
  String _language = 'English';
  String _transcript = 'Tap the microphone and start speaking';
  String? _error;

  String get _locale => switch (_language) {
        'Hindi' => 'hi-IN',
        'Hinglish' => 'hi-IN',
        _ => 'en-IN',
      };

  @override
  void initState() {
    super.initState();
    _initialize();
    _tts.setStartHandler(() {
      if (mounted) setState(() => _speaking = true);
    });
    _tts.setCompletionHandler(() {
      if (mounted) setState(() => _speaking = false);
    });
    _tts.setErrorHandler((_) {
      if (mounted) setState(() => _speaking = false);
    });
  }

  Future<void> _initialize() async {
    _available = await _speech.initialize(onError: (error) {
      if (mounted)
        setState(() {
          _error = error.errorMsg;
          _listening = false;
        });
    });
    if (mounted) setState(() {});
  }

  Future<void> _toggleListening() async {
    if (_listening) {
      await _speech.stop();
      if (mounted) setState(() => _listening = false);
      return;
    }
    if (!_available) {
      await _initialize();
      if (!_available) {
        setState(
            () => _error = 'Speech recognition is unavailable on this device.');
        return;
      }
    }
    setState(() {
      _error = null;
      _transcript = '';
      _listening = true;
    });
    await _speech.listen(
      listenOptions: stt.SpeechListenOptions(
        localeId: _locale,
        listenFor: const Duration(seconds: 45),
        pauseFor: const Duration(seconds: 4),
      ),
      onResult: (result) {
        if (!mounted) return;
        setState(() => _transcript = result.recognizedWords);
        if (result.finalResult && result.recognizedWords.trim().isNotEmpty) {
          unawaited(_submit(result.recognizedWords.trim()));
        }
      },
    );
  }

  Future<void> _submit(String prompt) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _listening = false;
      _error = null;
    });
    try {
      await _speech.stop();
      final answer = await widget.onPrompt(prompt);
      if (!_muted) {
        await _tts.setLanguage(_language == 'English' ? 'en-IN' : 'hi-IN');
        await _tts.speak(answer);
      }
      if (mounted) setState(() => _transcript = answer);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _speech.stop();
    _tts.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final active = _listening || _speaking || _busy;
    return Scaffold(
      appBar: AppBar(title: const Text('Voice conversation'), actions: [
        DropdownButtonHideUnderline(
            child: DropdownButton<String>(
          value: _language,
          items: const ['English', 'Hindi', 'Hinglish']
              .map((language) =>
                  DropdownMenuItem(value: language, child: Text(language)))
              .toList(),
          onChanged: (value) => setState(() => _language = value ?? _language),
        )),
        const SizedBox(width: 12),
      ]),
      body: SafeArea(
        child: Column(
          children: [
            const Spacer(),
            VoiceOrb(active: active),
            const SizedBox(height: 18),
            Text(
                _busy
                    ? 'Thinking'
                    : _speaking
                        ? 'Speaking'
                        : _listening
                            ? 'Listening'
                            : 'Ready',
                style: Theme.of(context).textTheme.titleMedium),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 30, vertical: 16),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 150),
                child: SingleChildScrollView(
                    child: Text(_transcript,
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                            color: Theme.of(context).hintColor, height: 1.5))),
              ),
            ),
            if (_error != null)
              Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Text(_error!,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          color: Theme.of(context).colorScheme.error))),
            const Spacer(),
            Padding(
              padding: const EdgeInsets.fromLTRB(28, 12, 28, 30),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _VoiceControl(
                      icon: _muted
                          ? Icons.volume_off_rounded
                          : Icons.volume_up_rounded,
                      label: 'Speaker',
                      selected: _muted,
                      onTap: () => setState(() => _muted = !_muted)),
                  FloatingActionButton.large(
                    heroTag: 'voice-mic',
                    onPressed: _busy ? null : _toggleListening,
                    backgroundColor: _listening
                        ? Theme.of(context).colorScheme.error
                        : Theme.of(context).colorScheme.primary,
                    foregroundColor: const Color(0xFF081216),
                    child: Icon(
                        _listening ? Icons.stop_rounded : Icons.mic_rounded,
                        size: 30),
                  ),
                  _VoiceControl(
                      icon: Icons.call_end_rounded,
                      label: 'End',
                      selected: false,
                      onTap: () => Navigator.pop(context)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _VoiceControl extends StatelessWidget {
  const _VoiceControl(
      {required this.icon,
      required this.label,
      required this.selected,
      required this.onTap});

  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Column(children: [
        IconButton.filledTonal(
          onPressed: onTap,
          icon: Icon(icon),
          style: IconButton.styleFrom(
            backgroundColor: selected
                ? Theme.of(context).colorScheme.primaryContainer
                : null,
          ),
        ),
        Text(label, style: Theme.of(context).textTheme.labelSmall),
      ]);
}
