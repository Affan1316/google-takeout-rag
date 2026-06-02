import '../../data/datasources/local_history_datasource.dart';
import '../../data/datasources/backend_process_datasource.dart';
import '../../data/datasources/backend_api_datasource.dart';
import '../../data/repositories/chat_history_repository_impl.dart';
import '../../data/repositories/backend_repository_impl.dart';
import '../../domain/repositories/chat_history_repository.dart';
import '../../domain/repositories/backend_repository.dart';
import '../../domain/usecases/chat_sessions_usecases.dart';
import '../../domain/usecases/db_credentials_usecases.dart';
import '../../domain/usecases/backend_process_usecases.dart';
import '../../domain/usecases/backend_api_usecases.dart';
import '../../presentation/controllers/chat_controller.dart';

class ServiceLocator {
  static final ServiceLocator instance = ServiceLocator._internal();

  ServiceLocator._internal();

  // Central dependencies
  late final LocalHistoryDataSource localHistoryDataSource;
  late final BackendProcessDataSource backendProcessDataSource;
  late final BackendApiDataSource backendApiDataSource;

  late final ChatHistoryRepository chatHistoryRepository;
  late final BackendRepository backendRepository;

  late final ChatSessionsUsecases chatSessionsUsecases;
  late final DbCredentialsUsecases dbCredentialsUsecases;
  late final BackendProcessUsecases backendProcessUsecases;
  late final BackendApiUsecases backendApiUsecases;

  late final ChatController chatController;

  void initialize() {
    localHistoryDataSource = LocalHistoryDataSource();
    backendProcessDataSource = BackendProcessDataSource();
    backendApiDataSource = BackendApiDataSource();

    chatHistoryRepository = ChatHistoryRepositoryImpl(
      localDataSource: localHistoryDataSource,
    );
    backendRepository = BackendRepositoryImpl(
      apiDataSource: backendApiDataSource,
      processDataSource: backendProcessDataSource,
    );

    chatSessionsUsecases = ChatSessionsUsecases(
      historyRepository: chatHistoryRepository,
      backendRepository: backendRepository,
    );
    dbCredentialsUsecases = DbCredentialsUsecases(
      historyRepository: chatHistoryRepository,
      backendRepository: backendRepository,
    );
    backendProcessUsecases = BackendProcessUsecases(
      repository: backendRepository,
    );
    backendApiUsecases = BackendApiUsecases(
      repository: backendRepository,
    );

    chatController = ChatController(
      chatSessionsUsecases: chatSessionsUsecases,
      dbCredentialsUsecases: dbCredentialsUsecases,
      backendProcessUsecases: backendProcessUsecases,
      backendApiUsecases: backendApiUsecases,
    );
  }
}
