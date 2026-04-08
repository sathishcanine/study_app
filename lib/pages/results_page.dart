// ignore_for_file: must_be_immutable

import 'package:audioplayers/audioplayers.dart';
import 'package:circular_countdown_timer/circular_countdown_timer.dart';
import 'package:flutter/material.dart';
import 'package:page_transition/page_transition.dart';
import 'package:study_app/constants.dart';
import 'package:study_app/models/question.dart';
import 'package:study_app/pages/firebase_services.dart/firestore.dart';
import 'package:study_app/pages/home_page.dart';
import 'package:study_app/pages/question_page.dart';
import 'package:study_app/widgets/analysesWidger.dart';
import 'package:study_app/widgets/correction_widget.dart';
import 'package:study_app/widgets/score_widget.dart';
import 'package:dashed_circular_progress_bar/dashed_circular_progress_bar.dart';

class ResultPage extends StatefulWidget {
  const ResultPage({
    super.key,
    required this.playerResults,
    required this.questions,
    required this.type,
    required this.email,
    required this.playerSelectedResponses,
    required this.diffiuclty,
    required this.catId,
  });

  final List<String> playerResults;
  final List<Question> questions;
  final String type, email, diffiuclty, catId;
  final List<Map<String, dynamic>> playerSelectedResponses;

  @override
  State<ResultPage> createState() => _ResultPageState();
}

class _ResultPageState extends State<ResultPage> {
  late final ValueNotifier<double> _valueNotifier;
  late final AudioPlayer _player;
  late final int score;
  late final int totalQuestions;
  late final int correct;
  late final int skipped;
  late final int wrong;

  @override
  void initState() {
    super.initState();
    _valueNotifier = ValueNotifier(0);
    _player = AudioPlayer();
    int s = 0, c = 0, sk = 0, w = 0;
    final n = widget.playerResults.length;
    for (String response in widget.playerResults) {
      if (response == "true") {
        s += 10;
        c++;
      } else if (response == "false") {
        w++;
      } else {
        sk++;
      }
    }
    score = s;
    totalQuestions = n;
    correct = c;
    skipped = sk;
    wrong = w;
    updateUserDetails(
      id: widget.email,
      score: score,
      questionNumbers: widget.questions.length - skipped,
      correctAnswers: correct,
      catName: widget.questions[0].name,
      questionlength: widget.questions.length,
      difficulty: widget.diffiuclty,
      date: DateTime.now(),
    ).catchError((_) {});
    _playSound();
  }

  Future<void> _playSound() async {
    const soundPath =
        "sounds/level-complete-mobile-game-app-locran-1-00-06.mp3";
    await _player.play(AssetSource(soundPath));
  }

  @override
  void dispose() {
    _valueNotifier.dispose();
    _player.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: Container(
        decoration: const BoxDecoration(
          image: DecorationImage(
            image: AssetImage("assets/images/score.png"),
          ),
        ),
        child: Scaffold(
          backgroundColor: Colors.transparent,
          appBar: AppBar(
            automaticallyImplyLeading: false,
            backgroundColor: Colors.transparent,
            actions: [
              IconButton(
                icon: const Icon(
                  Icons.home,
                  color: Colors.white,
                ),
                onPressed: () {
                  Navigator.popAndPushNamed(
                    context,
                    HomePage.id,
                    arguments: widget.email,
                  );
                },
              ),
              const SizedBox(
                width: 5,
              )
            ],
          ),
          body: Column(
            children: [
              Center(
                child: ScoreWidget(
                  score: score,
                ),
              ),
              Padding(
                padding:
                    const EdgeInsets.symmetric(vertical: 10, horizontal: 15),
                child: Material(
                  elevation: 3,
                  borderRadius: BorderRadius.circular(24),
                  color: Colors.transparent,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        vertical: 25, horizontal: 25),
                    width: double.infinity,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(24),
                      color: Colors.white,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          "Test resulat",
                          style: TextStyle(
                            color: const Color(0xff999999).withOpacity(0.6),
                            fontSize: 20,
                            fontFamily: kFontText,
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 20),
                          child: DashedCircularProgressBar.aspectRatio(
                            aspectRatio: 3.3,
                            valueNotifier: _valueNotifier,
                            progress: totalQuestions == 0
                                ? 0
                                : (correct * 100) / totalQuestions,
                            maxProgress: 100,
                            corners: StrokeCap.butt,
                            foregroundColor: const Color(0xffA76AE4),
                            backgroundColor: const Color(0xffeeeeee),
                            foregroundStrokeWidth: 13,
                            backgroundStrokeWidth: 13,
                            animation: true,
                            child: Center(
                              child: ValueListenableBuilder(
                                valueListenable: _valueNotifier,
                                builder: (_, double value, __) => Text(
                                  '${value.toInt()}%',
                                  style: TextStyle(
                                    color: const Color(0xff9D57E3),
                                    fontWeight: FontWeight.bold,
                                    fontSize: 23,
                                    fontFamily: kFontText,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                        Text(
                          "Quiz analyses ",
                          style: TextStyle(
                            color: const Color(0xff999999).withOpacity(0.6),
                            fontSize: 20,
                            fontFamily: kFontText,
                          ),
                        ),
                        const SizedBox(
                          height: 20,
                        ),
                        Row(
                          children: [
                            AnaylsesWidget(
                              number: totalQuestions,
                              label: "Total Questions",
                              textColor: const Color(0xffA42FC1),
                              containerColor: const Color(0xffA42FC1),
                            ),
                            const Spacer(
                              flex: 1,
                            ),
                            AnaylsesWidget(
                              number: skipped,
                              label: "Skipped",
                              textColor: const Color(0xff6680DB),
                              containerColor: const Color(0xff6680DB),
                            ),
                            const Spacer(
                              flex: 1,
                            ),
                          ],
                        ),
                        const SizedBox(
                          height: 20,
                        ),
                        Row(
                          children: [
                            AnaylsesWidget(
                              number: correct,
                              label: "Correct",
                              textColor: const Color(0xff1F8435),
                              containerColor: const Color(0xff1F8435),
                            ),
                            const Spacer(
                              flex: 2,
                            ),
                            AnaylsesWidget(
                              number: wrong,
                              label: "Wrong",
                              textColor: const Color(0xffFA3939),
                              containerColor: const Color(0xffFA3939),
                            ),
                            const Spacer(
                              flex: 1,
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.only(
                    right: 47, left: 47, top: 30, bottom: 15),
                child: MaterialButton(
                  elevation: 5,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(5),
                  ),
                  onPressed: () {
                    Navigator.push(
                      context,
                      PageTransition(
                        child: QuestionPage(
                          catId: widget.catId,
                          difficulty: widget.diffiuclty,
                          questionNumber: widget.questions.length.toString(),
                          type: widget.type,
                          email: widget.email,
                        ),
                        type: PageTransitionType.topToBottom,
                        duration: const Duration(milliseconds: 300),
                      ),
                    );
                  },
                  height: 50,
                  minWidth: double.infinity,
                  color: kPrimaryColor,
                  child: const Text(
                    "Play again",
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                      fontFamily: "Ubuntu",
                      color: Colors.white,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
              InkWell(
                onTap: () {
                  Navigator.push(
                    context,
                    PageTransition(
                      child: CorrectionUi(
                        playerSlectedResponses: widget.playerSelectedResponses,
                        playerResults: widget.playerResults,
                        controller: CountDownController(),
                        questions: widget.questions,
                        questionsNumber: widget.questions.length,
                        type: widget.type,
                      ),
                      type: PageTransitionType.bottomToTop,
                      duration: const Duration(milliseconds: 300),
                    ),
                  );
                },
                child: Text(
                  "Check your Answers",
                  style: TextStyle(
                    fontSize: 16,
                    fontFamily: "Ubuntu",
                    fontWeight: FontWeight.w500,
                    color: kPrimaryColor,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
