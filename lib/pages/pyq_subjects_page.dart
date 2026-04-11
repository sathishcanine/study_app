import 'package:flutter/material.dart';
import 'package:page_transition/page_transition.dart';
import 'package:study_app/constants.dart';
import 'package:study_app/pages/pyq_questions_page.dart';
import 'package:study_app/services/auth_storage.dart';
import 'package:study_app/services/study_api.dart';

class PyqSubjectsPage extends StatefulWidget {
  const PyqSubjectsPage({
    super.key,
    required this.email,
  });

  final String email;

  @override
  State<PyqSubjectsPage> createState() => _PyqSubjectsPageState();
}

class _PyqSubjectsPageState extends State<PyqSubjectsPage> {
  late Future<Map<String, dynamic>> _subjectsFuture;

  @override
  void initState() {
    super.initState();
    _subjectsFuture = _fetchSubjects();
  }

  Future<Map<String, dynamic>> _fetchSubjects() async {
    final token = await AuthStorage.getToken();
    if (token == null || token.isEmpty) {
      throw StudyApiException('Session expired. Please log in again.');
    }
    return StudyApi().getPyqSubjects(token: token);
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
          title: const Text(
            'Previous Year Questions',
            style: TextStyle(color: Colors.white),
          ),
          backgroundColor: Colors.transparent,
        ),
        body: FutureBuilder<Map<String, dynamic>>(
          future: _subjectsFuture,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    snapshot.error.toString(),
                    style: const TextStyle(color: Colors.white),
                    textAlign: TextAlign.center,
                  ),
                ),
              );
            }
            final payload = snapshot.data ?? {};
            final subjects = (payload['subjects'] as List<dynamic>? ?? [])
                .cast<Map<String, dynamic>>();
            if (subjects.isEmpty) {
              return const Center(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Text(
                    'No PYQ subjects available yet.\nAsk admin to run PYQ ingestion.',
                    style: TextStyle(color: Colors.white),
                    textAlign: TextAlign.center,
                  ),
                ),
              );
            }
            return Container(
              margin: const EdgeInsets.all(12),
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(26),
              ),
              child: GridView.builder(
                itemCount: subjects.length,
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                  childAspectRatio: 1.08,
                ),
                itemBuilder: (context, index) {
                  final s = subjects[index];
                  final subjectName = (s['subject_name'] ?? '').toString();
                  final subjectSlug = (s['subject_slug'] ?? '').toString();
                  final totalQuestions = (s['total_questions'] as num?)?.toInt() ?? 0;
                  final totalDocs = (s['total_documents'] as num?)?.toInt() ?? 0;
                  return InkWell(
                    borderRadius: BorderRadius.circular(18),
                    onTap: () {
                      Navigator.push(
                        context,
                        PageTransition(
                          type: PageTransitionType.rightToLeft,
                          duration: const Duration(milliseconds: 260),
                          child: PyqQuestionsPage(
                            email: widget.email,
                            subjectSlug: subjectSlug,
                            subjectName: subjectName,
                          ),
                        ),
                      );
                    },
                    child: Ink(
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(18),
                        gradient: const LinearGradient(
                          colors: [Color(0xffF8F4FF), Color(0xffEEE3FF)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                        border: Border.all(
                          color: const Color(0xffD9C5FF),
                        ),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const CircleAvatar(
                              radius: 16,
                              backgroundColor: Color(0xff8251DE),
                              child: Icon(Icons.menu_book_rounded, color: Colors.white, size: 18),
                            ),
                            const SizedBox(height: 10),
                            Text(
                              subjectName,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w700,
                                color: Color(0xff3D2664),
                              ),
                            ),
                            const Spacer(),
                            Text(
                              '$totalQuestions questions',
                              style: const TextStyle(
                                fontSize: 13,
                                color: Color(0xff6A4EA3),
                              ),
                            ),
                            Text(
                              '$totalDocs PDFs',
                              style: const TextStyle(
                                fontSize: 12,
                                color: Color(0xff866DB8),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  );
                },
              ),
            );
          },
        ),
      ),
    );
  }
}
