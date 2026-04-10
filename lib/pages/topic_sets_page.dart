import 'package:flutter/material.dart';
import 'package:study_app/constants.dart';
import 'package:study_app/pages/topic_set_leaderboard_page.dart';
import 'package:study_app/pages/topic_set_question_page.dart';
import 'package:study_app/services/auth_storage.dart';
import 'package:study_app/services/study_api.dart';

class TopicSetsPage extends StatefulWidget {
  const TopicSetsPage({
    super.key,
    required this.subjectName,
    required this.subjectKey,
    required this.email,
  });

  final String subjectName;
  final String subjectKey;
  final String email;

  @override
  State<TopicSetsPage> createState() => _TopicSetsPageState();
}

class _TopicSetsPageState extends State<TopicSetsPage> {
  late Future<Map<String, dynamic>> _setsFuture;
  late Future<Map<String, dynamic>> _completedFuture;

  @override
  void initState() {
    super.initState();
    _setsFuture = _fetchSets();
    _completedFuture = _fetchCompletedSets();
  }

  Future<Map<String, dynamic>> _fetchSets() async {
    final token = await AuthStorage.getToken();
    if (token == null || token.isEmpty) {
      throw StudyApiException('Session expired. Please log in again.');
    }
    return StudyApi().getSubjectSets(
      token: token,
      examType: 'TNPSC',
      subject: widget.subjectKey,
    );
  }

  Future<Map<String, dynamic>> _fetchCompletedSets() async {
    final token = await AuthStorage.getToken();
    if (token == null || token.isEmpty) {
      throw StudyApiException('Session expired. Please log in again.');
    }
    return StudyApi().getCompletedTopicSets(
      token: token,
      examType: 'TNPSC',
      subject: widget.subjectKey,
    );
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Container(
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
              widget.subjectName,
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
              child: Column(
                children: [
                  const SizedBox(height: 16),
                  const TabBar(
                    indicatorColor: Color(0xff8251DE),
                    labelColor: Color(0xff462C78),
                    unselectedLabelColor: Colors.black54,
                    tabs: [
                      Tab(text: 'Tests'),
                      Tab(text: 'Completed'),
                    ],
                  ),
                  Expanded(
                    child: TabBarView(
                      children: [
                        FutureBuilder<Map<String, dynamic>>(
                          future: _setsFuture,
                          builder: (context, snapshot) {
                            if (snapshot.connectionState ==
                                ConnectionState.waiting) {
                              return const Center(
                                child: CircularProgressIndicator(),
                              );
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
                            final allSets = (payload['sets'] as List<dynamic>? ?? [])
                                .cast<Map<String, dynamic>>();
                            final sets = allSets
                                .where((s) => (s['attempted_by_me'] ?? false) != true)
                                .toList();
                            if (sets.isEmpty) {
                              return const Center(
                                child: Text('No available tests.'),
                              );
                            }
                            return ListView.builder(
                              padding: const EdgeInsets.all(12),
                              itemCount: sets.length,
                              itemBuilder: (context, index) {
                                final set = sets[index];
                                final setNo = set['set_no'] ?? '-';
                                final numQuestions = set['num_questions'] ?? 0;
                                final status = (set['job_status'] ?? '').toString();
                                final isCompleted = status.toLowerCase() == 'completed';
                                return Card(
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: ListTile(
                                    title: Text('Set $setNo'),
                                    subtitle: Text(
                                      '${set['topic_slug']}  •  $numQuestions questions',
                                    ),
                                    trailing: const Icon(Icons.chevron_right),
                                    enabled: isCompleted,
                                    onTap: !isCompleted
                                        ? null
                                        : () {
                                            Navigator.push(
                                              context,
                                              MaterialPageRoute(
                                                builder: (_) => TopicSetQuestionPage(
                                                  email: widget.email,
                                                  subjectName: widget.subjectName,
                                                  subjectKey: widget.subjectKey,
                                                  topicSlug: (set['topic_slug'] ?? '')
                                                      .toString(),
                                                  setNo:
                                                      (set['set_no'] as num?)?.toInt() ??
                                                          1,
                                                  setId: (set['id'] ?? '').toString(),
                                                  examType: (set['exam_type'] ?? 'TNPSC')
                                                      .toString(),
                                                ),
                                              ),
                                            );
                                          },
                                  ),
                                );
                              },
                            );
                          },
                        ),
                        FutureBuilder<Map<String, dynamic>>(
                          future: _completedFuture,
                          builder: (context, snapshot) {
                            if (snapshot.connectionState ==
                                ConnectionState.waiting) {
                              return const Center(
                                child: CircularProgressIndicator(),
                              );
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
                            final completed =
                                (payload['completed_sets'] as List<dynamic>? ?? [])
                                    .cast<Map<String, dynamic>>();
                            if (completed.isEmpty) {
                              return const Center(
                                child: Text('No completed tests yet.'),
                              );
                            }
                            return ListView.builder(
                              padding: const EdgeInsets.all(12),
                              itemCount: completed.length,
                              itemBuilder: (context, index) {
                                final row = completed[index];
                                final set = (row['set'] as Map<String, dynamic>? ?? {});
                                final setNo = set['set_no'] ?? '-';
                                final rank = set['my_rank'] ?? '-';
                                final takers = set['total_takers'] ?? 0;
                                final score = set['my_score'] ?? 0;
                                return Card(
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: ListTile(
                                    title: Text('Set $setNo'),
                                    subtitle: Text(
                                      'Rank: $rank / $takers  •  Score: $score',
                                    ),
                                    trailing: const Icon(Icons.chevron_right),
                                    onTap: () {
                                      Navigator.push(
                                        context,
                                        MaterialPageRoute(
                                          builder: (_) => TopicSetLeaderboardPage(
                                            setId: (set['id'] ?? '').toString(),
                                            subjectName: widget.subjectName,
                                            setNo:
                                                (set['set_no'] as num?)?.toInt() ?? 1,
                                          ),
                                        ),
                                      );
                                    },
                                  ),
                                );
                              },
                            );
                          },
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
