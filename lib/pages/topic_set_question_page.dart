import 'package:circular_countdown_timer/circular_countdown_timer.dart';
import 'package:flutter/material.dart';
import 'package:study_app/constants.dart';
import 'package:study_app/models/question.dart';
import 'package:study_app/services/auth_storage.dart';
import 'package:study_app/services/study_api.dart';
import 'package:study_app/widgets/loading_widget.dart';
import 'package:study_app/widgets/questions_display_widget.dart';

class TopicSetQuestionPage extends StatefulWidget {
  const TopicSetQuestionPage({
    super.key,
    required this.email,
    required this.subjectName,
    required this.subjectKey,
    required this.topicSlug,
    required this.setNo,
    required this.setId,
    this.examType = 'TNPSC',
    this.lang = 'en',
  });

  final String email;
  final String subjectName;
  final String subjectKey;
  final String topicSlug;
  final int setNo;
  final String setId;
  final String examType;
  final String lang;

  @override
  State<TopicSetQuestionPage> createState() => _TopicSetQuestionPageState();
}

class _TopicSetQuestionPageState extends State<TopicSetQuestionPage> {
  final CountDownController controller = CountDownController();

  Future<List<Question>> _fetchQuestions() async {
    final token = await AuthStorage.getToken();
    if (token == null || token.isEmpty) {
      throw StudyApiException('Session expired. Please log in again.');
    }
    final payload = await StudyApi().getTopicQuestions(
      token: token,
      topicSlug: widget.topicSlug,
      examType: widget.examType,
      subject: widget.subjectKey,
      setNo: widget.setNo,
      lang: widget.lang,
    );
    final items =
        (payload['questions'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
    return items.map(_toQuestion).toList();
  }

  Question _toQuestion(Map<String, dynamic> json) {
    final options = (json['options'] as List<dynamic>? ?? [])
        .map((e) => e.toString())
        .toList();
    final answer = (json['answer'] ?? '').toString();
    final incorrect = options.where((o) => o != answer).toList();
    return Question(
      type: 'multiple',
      difficulty: (json['difficulty'] ?? 'medium').toString(),
      correctAnswer: answer,
      incorrectAnswers: incorrect,
      question: (json['question_text'] ?? '').toString(),
      name: widget.subjectName,
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: Container(
        decoration: const BoxDecoration(
          image: DecorationImage(
            image: AssetImage("assets/images/Question_background.png"),
          ),
        ),
        child: FutureBuilder<List<Question>>(
          future: _fetchQuestions(),
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const LoadingWidget(
                color: Colors.deepPurple,
              );
            }
            if (snapshot.hasError) {
              return Scaffold(
                backgroundColor: Colors.transparent,
                body: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      snapshot.error.toString(),
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: Colors.white,
                        fontFamily: kFontText,
                      ),
                    ),
                  ),
                ),
              );
            }

            final questions = snapshot.data ?? <Question>[];
            if (questions.isEmpty) {
              return const Scaffold(
                backgroundColor: Colors.transparent,
                body: Center(
                  child: Text(
                    'No questions found for this set.',
                    style: TextStyle(color: Colors.white),
                  ),
                ),
              );
            }

            return QuestionUi(
              email: widget.email,
              controller: controller,
              questions: questions,
              questionsNumber: questions.length,
              type: 'multiple',
              difficulty: 'mixed',
              catId: widget.subjectKey,
              questionNumber: questions.length.toString(),
              replayTopicSlug: widget.topicSlug,
              replaySetNo: widget.setNo,
              replaySetId: widget.setId,
              replayExamType: widget.examType,
              replaySubject: widget.subjectKey,
              replayLang: widget.lang,
              replaySubjectName: widget.subjectName,
            );
          },
        ),
      ),
    );
  }
}
