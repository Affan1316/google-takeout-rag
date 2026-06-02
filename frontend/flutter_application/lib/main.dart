import 'package:flutter/material.dart';
import 'core/theme/app_theme.dart';
import 'core/di/service_locator.dart';
import 'presentation/pages/chat_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // Initialize dependency injection
  ServiceLocator.instance.initialize();

  // Kick off controller initialization (backend auto-start, session loading)
  ServiceLocator.instance.chatController.initialize();

  runApp(const AIHistoryApp());
}

class AIHistoryApp extends StatelessWidget {
  const AIHistoryApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'History AI Agent',
      theme: AppTheme.darkTheme,
      home: ChatScreen(controller: ServiceLocator.instance.chatController),
      debugShowCheckedModeBanner: false,
    );
  }
}
