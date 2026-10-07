import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_service.dart';

class ScannerScreen extends StatefulWidget {
  const ScannerScreen({
    super.key,
    required this.api,
    required this.onUseText,
  });

  final ApiService api;
  final ValueChanged<String> onUseText;

  @override
  State<ScannerScreen> createState() => _ScannerScreenState();
}

class _ScannerScreenState extends State<ScannerScreen> {
  final ImagePicker _picker = ImagePicker();
  XFile? _image;
  String? _text;
  String? _error;
  bool _busy = false;

  Future<void> _scan(ImageSource source) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _text = null;
    });
    try {
      final image = await _picker.pickImage(
        source: source,
        maxWidth: 2400,
        maxHeight: 2400,
        imageQuality: 90,
      );
      if (image == null) return;

      await widget.api.checkScannerAccess();
      if (kIsWeb ||
          !{
            TargetPlatform.android,
            TargetPlatform.iOS,
          }.contains(defaultTargetPlatform)) {
        throw const ApiException(
          'On-device OCR is available in the Android and iOS app. '
          'No remote image analysis is configured.',
        );
      }

      final input = InputImage.fromFilePath(image.path);
      final latinRecognizer = TextRecognizer();
      final devanagariRecognizer = TextRecognizer(
        script: TextRecognitionScript.devanagiri,
      );
      try {
        final latin = await latinRecognizer.processImage(input);
        final devanagari = await devanagariRecognizer.processImage(input);
        if (!mounted) return;
        final text = latin.text.length >= devanagari.text.length
            ? latin.text.trim()
            : devanagari.text.trim();
        setState(() {
          _image = image;
          _text = text;
        });
      } finally {
        await latinRecognizer.close();
        await devanagariRecognizer.close();
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Document scanner')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(
              'Scan with your camera or select an image. '
              'Text recognition runs on-device; the image stays on this device.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 18),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                FilledButton.icon(
                  onPressed: _busy ? null : () => _scan(ImageSource.camera),
                  icon: const Icon(Icons.camera_alt_outlined),
                  label: const Text('Take photo'),
                ),
                OutlinedButton.icon(
                  onPressed: _busy ? null : () => _scan(ImageSource.gallery),
                  icon: const Icon(Icons.photo_library_outlined),
                  label: const Text('Choose image'),
                ),
              ],
            ),
            if (_busy) ...[
              const SizedBox(height: 24),
              const Center(child: CircularProgressIndicator()),
            ],
            if (_image case final image?) ...[
              const SizedBox(height: 20),
              Text(
                image.name,
                style: Theme.of(context).textTheme.labelLarge,
              ),
            ],
            if (_error case final error?) ...[
              const SizedBox(height: 18),
              SelectableText(
                error,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
            if (_text case final text?) ...[
              const SizedBox(height: 18),
              Text('Recognized text',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              SelectableText(
                text.isEmpty ? 'No readable text was found.' : text,
              ),
              if (text.isNotEmpty) ...[
                const SizedBox(height: 16),
                FilledButton.icon(
                  onPressed: () {
                    Navigator.of(context).pop();
                    widget.onUseText(
                      'Analyze this scanned text:\n\n${text.substring(0, text.length > 20000 ? 20000 : text.length)}',
                    );
                  },
                  icon: const Icon(Icons.auto_awesome_outlined),
                  label: const Text('Analyze with BISNU-X'),
                ),
              ],
            ],
            const SizedBox(height: 18),
            Text(
              'Scanner access requires an active paid plan. The image stays on '
              'this device. OCR text is sent to chat only when you choose Analyze.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}
