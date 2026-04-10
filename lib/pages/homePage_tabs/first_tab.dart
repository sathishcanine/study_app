import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:page_transition/page_transition.dart';
import 'package:study_app/data.dart';
import 'package:study_app/pages/topic_sets_page.dart';
import 'package:study_app/widgets/category_container.dart';

class FirstTab extends StatefulWidget {
  FirstTab({
    super.key,
    required this.updateIndex,
    required this.email,
  });
  final void Function(int, int?) updateIndex;
  final String email;

  @override
  State<FirstTab> createState() => _FirstTabState();
}

class _FirstTabState extends State<FirstTab> {
  final CategoriesData data = CategoriesData();
  final AudioPlayer player = AudioPlayer();

  String _toApiKey(String value) {
    return value.trim().toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), '_');
  }

  Future<void> playSound() async {
    String soundPath =
        "sounds/456601__bumpelsnake__select10.wav"; //You don't need to include assets/ because AssetSource assume that you have sound in your assets folder.
    await player.play(AssetSource(soundPath));
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: ListView.builder(
        itemCount: data.otherList.length,
        itemBuilder: (context, index) => GestureDetector(
          onTap: () {
            playSound();
            final subjectName = data.otherList[index]["name"] as String;
            final subjectKey = _toApiKey(subjectName);
            Navigator.push(
              context,
              PageTransition(
                child: TopicSetsPage(
                  subjectName: subjectName,
                  subjectKey: subjectKey,
                  email: widget.email,
                ),
                type: PageTransitionType.rightToLeft,
                duration: const Duration(milliseconds: 300),
              ),
            );
          },
          child: CatContainer(
            image: data.otherList[index]["image"],
            title: data.otherList[index]["name"],
            color: Colors.grey,
            questionsNumber:
                data.otherList[index]["total_questions"].toString(),
          ),
        ),
      ),
    );
  }
}
