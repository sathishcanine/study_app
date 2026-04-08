import 'package:study_app/services/auth_storage.dart';
import 'package:study_app/services/study_api.dart';

Future<Map<String, dynamic>> getUserDetails({required String id}) async {
  final token = await AuthStorage.getToken();
  if (token == null) {
    throw Exception('Session expired. Please log in again.');
  }
  return StudyApi().getProfile(token);
}

Future<void> updateUserDetails({
  required String id,
  required int score,
  required int questionNumbers,
  required int correctAnswers,
  required String catName,
  required int questionlength,
  required String difficulty,
  required DateTime date,
}) async {
  final token = await AuthStorage.getToken();
  if (token == null) return;
  await StudyApi().recordQuizResult(
    token: token,
    earnedScore: score,
    questionNumbers: questionNumbers,
    correctAnswers: correctAnswers,
    catName: catName,
    questionLength: questionlength,
    difficulty: difficulty,
    date: date,
  );
}
