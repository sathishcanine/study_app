import 'dart:async';

import 'package:flutter/material.dart';
import 'package:study_app/constants.dart';
import 'package:study_app/models/user.dart';
import 'package:study_app/pages/home_page.dart';
import 'package:study_app/services/study_api.dart';
import 'package:study_app/widgets/loading_widget.dart';

class LeaderBoardPage extends StatefulWidget {
  const LeaderBoardPage({super.key, required this.email});
  final String email;

  static String id = "/LeaderBoardPage";

  @override
  State<LeaderBoardPage> createState() => _LeaderBoardPageState();
}

class _LeaderBoardPageState extends State<LeaderBoardPage> {
  List<User> _users = [];
  Object? _error;
  bool _loading = true;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _refresh();
    _timer = Timer.periodic(const Duration(seconds: 10), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    try {
      final rows = await StudyApi().getLeaderboard();
      if (!mounted) return;
      setState(() {
        _users = rows.map((m) => User.fromjson(m)).toList();
        while (_users.length < 3) {
          _users.add(User(userName: '—', score: 0));
        }
        _error = null;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        body: const LoadingWidget(
          color: Colors.white,
        ),
        backgroundColor: kPrimaryColor,
      );
    }
    if (_error != null) {
      return Scaffold(
        backgroundColor: kPrimaryColor,
        body: Center(
          child: Text(
            _error.toString(),
            style: const TextStyle(color: Colors.white),
            textAlign: TextAlign.center,
          ),
        ),
      );
    }

    final users = _users;
    return PopScope(
      canPop: false,
      child: Scaffold(
        appBar: AppBar(
          backgroundColor: Colors.transparent,
          leading: Row(
            children: [
              const SizedBox(
                width: 5,
              ),
              IconButton(
                onPressed: () {
                  Navigator.popAndPushNamed(context, HomePage.id,
                      arguments: widget.email);
                },
                icon: const Icon(
                  Icons.arrow_back,
                  size: 30,
                  color: Colors.white,
                ),
              ),
            ],
          ),
        ),
        backgroundColor: kPrimaryColor,
        body: RefreshIndicator(
          color: kPrimaryColor,
          onRefresh: _refresh,
          child: Padding(
            padding: const EdgeInsets.only(top: 0, bottom: 0),
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 40),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      LeaderBoardContainer(
                        color: const Color(0xFFC0C0C0),
                        size: 12,
                        rank: 2,
                        score: users[1].score,
                        image: "assets/icons/knight.png",
                        name: users[1].userName,
                        bottom: 20,
                        width: 50,
                        height: 50,
                      ),
                      LeaderBoardContainer(
                        color: const Color(0xFFFFD700),
                        size: 14,
                        rank: 1,
                        score: users[0].score,
                        width: 70,
                        height: 70,
                        bottom: 50,
                        image: "assets/icons/king.png",
                        name: users[0].userName,
                      ),
                      LeaderBoardContainer(
                        color: const Color(0xFFCD7F32),
                        size: 12,
                        width: 50,
                        height: 50,
                        rank: 3,
                        score: users[2].score,
                        bottom: 20,
                        image: "assets/icons/jester.png",
                        name: users[2].userName,
                      )
                    ],
                  ),
                ),
                Expanded(
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 3,
                      vertical: 20,
                    ),
                    decoration: const BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.only(
                        topLeft: Radius.circular(40),
                        topRight: Radius.circular(40),
                      ),
                    ),
                    child: users.length <= 3
                        ? ListView(
                            physics: const AlwaysScrollableScrollPhysics(),
                            children: const [],
                          )
                        : ListView.builder(
                            physics: const AlwaysScrollableScrollPhysics(),
                            itemCount: users.length - 3,
                            itemBuilder: (context, index) => ListTile(
                              trailing: Container(
                                width: 60,
                                height: 26,
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(20),
                                  color: const Color(0xffAD8AE8),
                                ),
                                child: Center(
                                  child: Text(
                                    "${users[index + 3].score}",
                                    style: const TextStyle(
                                        fontSize: 15,
                                        fontFamily: "DM Sans",
                                        color: Color(0xff2B262D)),
                                  ),
                                ),
                              ),
                              leading: Container(
                                width: 32,
                                height: 32,
                                decoration: const BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: Color(0xffAD8AE8),
                                ),
                                child: Center(
                                  child: Text(
                                    "${index + 4}",
                                    style: const TextStyle(
                                      fontSize: 20,
                                      fontFamily: "Oldenburg",
                                      color: Color(0xff2B262D)),
                                  ),
                                ),
                              ),
                              title: Text(
                                users[index + 3].userName,
                                style: const TextStyle(
                                    fontSize: 20,
                                    fontFamily: "Oldenburg",
                                    color: Color(0xff2B262D)),
                              ),
                            ),
                          ),
                  ),
                )
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class LeaderBoardContainer extends StatelessWidget {
  const LeaderBoardContainer({
    super.key,
    required this.image,
    required this.name,
    required this.rank,
    required this.score,
    required this.size,
    required this.color,
    required this.bottom,
    required this.width,
    required this.height,
  });
  final String name, image;
  final int rank, score;
  final double size, bottom, width, height;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          name,
          style: TextStyle(
            color: Colors.white,
            fontFamily: kFontText,
            fontSize: size,
            fontWeight: FontWeight.w600,
          ),
        ),
        Container(
          margin: const EdgeInsets.only(bottom: 10, top: 5),
          padding: const EdgeInsetsDirectional.all(10),
          decoration: BoxDecoration(
            color: const Color(0xffE4D9F8),
            shape: BoxShape.circle,
            border: Border.all(color: color, width: 3),
          ),
          child: Image.asset(
            image,
            width: 70,
            height: 70,
          ),
        ),
        Container(
          width: 70,
          padding: EdgeInsets.only(bottom: bottom),
          decoration: const BoxDecoration(
            color: Color(0xffAD8AE8),
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(20),
              topRight: Radius.circular(20),
            ),
          ),
          child: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                Text(
                  "$rank",
                  style: const TextStyle(
                    fontSize: 65,
                    fontWeight: FontWeight.bold,
                    fontFamily: "DM Sans",
                    color: Colors.white,
                  ),
                ),
                Text(
                  "${score}pts",
                  style: TextStyle(
                    fontSize: 10,
                    fontFamily: kFontText,
                    color: Colors.white,
                  ),
                ),
                const SizedBox(
                  height: 5,
                ),
              ],
            ),
          ),
        )
      ],
    );
  }
}
