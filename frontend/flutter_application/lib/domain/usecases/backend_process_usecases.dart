import '../repositories/backend_repository.dart';

class BackendProcessUsecases {
  final BackendRepository repository;

  BackendProcessUsecases({required this.repository});

  Future<bool> checkBackendOnline() async {
    return repository.checkBackendOnline();
  }

  Future<Map<String, dynamic>> fetchBackendStatus() async {
    return repository.fetchBackendStatus();
  }

  Future<void> startBackendProcess({
    required void Function(String) onLog,
    required void Function(int) onExit,
  }) async {
    await repository.cleanPortConflict();
    await repository.startBackendProcess(onLog: onLog, onExit: onExit);
  }

  void shutdownBackendProcess() {
    repository.shutdownBackendProcess();
  }
}
