class ChatMessage {
  ChatMessage({required this.role, required this.content, DateTime? createdAt})
      : createdAt = createdAt ?? DateTime.now();

  final String role;
  String content;
  final DateTime createdAt;

  bool get isUser => role == 'user';
}
