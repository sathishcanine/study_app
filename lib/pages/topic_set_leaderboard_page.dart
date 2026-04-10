import 'package:flutter/material.dart';
import 'package:study_app/constants.dart';
import 'package:study_app/services/auth_storage.dart';
import 'package:study_app/services/study_api.dart';

class TopicSetLeaderboardPage extends StatefulWidget {
  const TopicSetLeaderboardPage({
    super.key,
    required this.setId,
    required this.subjectName,
    required this.setNo,
  });

  final String setId;
  final String subjectName;
  final int setNo;

  @override
  State<TopicSetLeaderboardPage> createState() => _TopicSetLeaderboardPageState();
}

class _TopicSetLeaderboardPageState extends State<TopicSetLeaderboardPage> {
  late Future<Map<String, dynamic>> _future;
  String? _myEmail;

  @override
  void initState() {
    super.initState();
    AuthStorage.getEmail().then((v) {
      if (!mounted) return;
      setState(() => _myEmail = v?.trim().toLowerCase());
    });
    _future = _fetch();
  }

  Future<Map<String, dynamic>> _fetch() async {
    final token = await AuthStorage.getToken();
    if (token == null || token.isEmpty) {
      throw StudyApiException('Session expired. Please log in again.');
    }
    return StudyApi().getTopicSetLeaderboard(token: token, setId: widget.setId);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [kPrimaryColor, const Color(0xff5C3B7E)],
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
        ),
      ),
      child: Scaffold(
        backgroundColor: Colors.transparent,
        appBar: AppBar(
          backgroundColor: Colors.transparent,
          title: Text(
            '${widget.subjectName} • Set ${widget.setNo}',
            style: const TextStyle(color: Colors.white),
          ),
        ),
        body: Padding(
          padding: const EdgeInsets.all(12),
          child: Container(
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(24),
            ),
            child: FutureBuilder<Map<String, dynamic>>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (snapshot.hasError) {
                  return Center(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Text(
                        snapshot.error.toString(),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  );
                }
                final payload = snapshot.data!;
                final totalTakers = payload['total_takers'] ?? 0;
                final entries =
                    (payload['entries'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
                return Column(
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                      child: Row(
                        children: [
                          Text(
                            'Total Takers: $totalTakers',
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                        ],
                      ),
                    ),
                    const Divider(height: 1),
                    Expanded(
                      child: ListView.builder(
                        padding: const EdgeInsets.all(12),
                        itemCount: entries.length,
                        itemBuilder: (context, index) {
                          final e = entries[index];
                          final email = (e['email'] ?? '').toString();
                          final isMe =
                              _myEmail != null && email.toLowerCase() == _myEmail;
                          return Card(
                            color: isMe ? const Color(0xffEFE5FF) : null,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: ListTile(
                              leading: CircleAvatar(
                                backgroundColor: isMe
                                    ? const Color(0xffC7A8FC)
                                    : const Color(0xffE3D8F7),
                                child: Text('${e['rank'] ?? '-'}'),
                              ),
                              title: Text(
                                '${(e['username'] ?? 'User').toString()}${isMe ? " (You)" : ""}',
                                style: TextStyle(
                                  fontWeight:
                                      isMe ? FontWeight.w700 : FontWeight.w500,
                                ),
                              ),
                              subtitle: Text(
                                'Score: ${e['score'] ?? 0} • Correct: ${e['correct_answers'] ?? 0}/${e['total_questions'] ?? 0}',
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ),
      ),
    );
  }
}
