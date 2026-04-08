// ignore_for_file: use_key_in_widget_constructors, must_be_immutable
import 'package:flutter/material.dart';
import 'package:study_app/constants.dart';
import 'package:study_app/pages/firebase_services.dart/firestore.dart';
import 'package:study_app/widgets/home_page_widget.dart';
import 'package:study_app/widgets/loading_widget.dart';

class HomePage extends StatefulWidget {
  static String id = "/home_page";

  const HomePage({
    super.key,
    required this.emails,
    required this.first,
  });

  final bool first;
  final String emails;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  Future<Map<String, dynamic>>? _profileFuture;
  String? _email;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_profileFuture != null) return;

    if (widget.first) {
      _email = widget.emails;
    } else {
      _email = ModalRoute.of(context)?.settings.arguments as String?;
    }

    if (_email == null || _email!.isEmpty) {
      return;
    }

    _profileFuture = getUserDetails(id: _email!);
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: _profileFuture == null
          ? Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    kPrimaryColor,
                    const Color(0xff5C3B7E),
                  ],
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                ),
              ),
              child: const LoadingWidget(
                color: Colors.white,
              ),
            )
          : FutureBuilder<Map<String, dynamic>>(
              future: _profileFuture,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [
                          kPrimaryColor,
                          const Color(0xff5C3B7E),
                        ],
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                      ),
                    ),
                    child: const LoadingWidget(
                      color: Colors.white,
                    ),
                  );
                } else if (snapshot.hasData) {
                  final data = snapshot.data!;
                  final username = data["username"] as String?;
                  final score = data["score"] as int;
                  return HomePageWidget(
                    data: data,
                    username: username,
                    email: _email,
                    score: score,
                    first: widget.first,
                  );
                } else {
                  return Text(snapshot.error.toString());
                }
              },
            ),
    );
  }
}
