import 'package:flutter/material.dart';
import 'package:study_app/constants.dart';
import 'package:study_app/services/auth_storage.dart';
import 'package:study_app/services/study_api.dart';

class PyqQuestionsPage extends StatefulWidget {
  const PyqQuestionsPage({
    super.key,
    required this.email,
    required this.subjectSlug,
    required this.subjectName,
  });

  final String email;
  final String subjectSlug;
  final String subjectName;

  @override
  State<PyqQuestionsPage> createState() => _PyqQuestionsPageState();
}

class _PyqQuestionsPageState extends State<PyqQuestionsPage> {
  String? _token;
  bool _loading = true;
  String? _error;

  List<int> _years = const [];
  List<String> _topics = const [];
  int? _selectedYear;
  String? _selectedTopic;

  final Map<String, List<Map<String, dynamic>>> _pageCache = {};
  final Map<String, int> _totalCache = {};

  int _currentPage = 1;
  int _limit = 20;
  int _questionIndex = 0;
  List<Map<String, dynamic>> _questions = const [];
  int _total = 0;

  String _cacheKey(int page, int limit, int? year, String? topic) {
    return 'p=$page|l=$limit|y=${year ?? "all"}|t=${(topic ?? "all").trim()}|src=auto';
  }

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    try {
      final token = await AuthStorage.getToken();
      if (token == null || token.isEmpty) {
        throw StudyApiException('Session expired. Please log in again.');
      }
      _token = token;
      final filters = await StudyApi().getPyqFilters(
        token: token,
        subjectSlug: widget.subjectSlug,
      );
      _years = (filters['years'] as List<dynamic>? ?? []).map((e) => (e as num).toInt()).toList();
      _topics = (filters['topics'] as List<dynamic>? ?? filters['subtopics'] as List<dynamic>? ?? [])
          .map((e) => e.toString())
          .toList();
      await _loadPage(resetIndex: true);
    } catch (e) {
      _error = e.toString();
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  Future<void> _loadPage({bool resetIndex = false}) async {
    final token = _token;
    if (token == null) return;
    final key = _cacheKey(_currentPage, _limit, _selectedYear, _selectedTopic);
    if (_pageCache.containsKey(key)) {
      setState(() {
        _questions = _pageCache[key] ?? const [];
        _total = _totalCache[key] ?? 0;
        if (resetIndex || _questionIndex >= _questions.length) {
          _questionIndex = 0;
        }
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final payload = await StudyApi().getPyqQuestions(
        token: token,
        subjectSlug: widget.subjectSlug,
        page: _currentPage,
        limit: _limit,
        year: _selectedYear,
        topic: _selectedTopic,
        source: 'auto',
      );
      final rows = (payload['questions'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
      _pageCache[key] = rows;
      _totalCache[key] = (payload['total'] as num?)?.toInt() ?? 0;
      setState(() {
        _questions = rows;
        _total = _totalCache[key] ?? 0;
        if (resetIndex || _questionIndex >= _questions.length) {
          _questionIndex = 0;
        }
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
      });
    } finally {
      setState(() {
        _loading = false;
      });
    }
  }

  Future<void> _applyFilters({int? year, String? topic}) async {
    setState(() {
      _selectedYear = year;
      _selectedTopic = topic;
      _currentPage = 1;
      _questionIndex = 0;
    });
    await _loadPage(resetIndex: true);
  }

  void _nextQuestion() {
    if (_questionIndex + 1 < _questions.length) {
      setState(() => _questionIndex += 1);
      return;
    }
    final seen = _currentPage * _limit;
    if (seen >= _total) return;
    setState(() {
      _currentPage += 1;
      _questionIndex = 0;
    });
    _loadPage(resetIndex: true);
  }

  void _prevQuestion() {
    if (_questionIndex > 0) {
      setState(() => _questionIndex -= 1);
      return;
    }
    if (_currentPage <= 1) return;
    setState(() {
      _currentPage -= 1;
      _questionIndex = 0;
    });
    _loadPage(resetIndex: false);
  }

  @override
  Widget build(BuildContext context) {
    final hasRows = _questions.isNotEmpty && _questionIndex < _questions.length;
    final current = hasRows ? _questions[_questionIndex] : <String, dynamic>{};

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
            '${widget.subjectName} PYQ',
            style: const TextStyle(color: Colors.white),
          ),
        ),
        body: _loading && _questions.isEmpty
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Text(
                        _error!,
                        style: const TextStyle(color: Colors.white),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  )
                : Column(
                    children: [
                      _buildFilters(),
                      Expanded(
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Container(
                            width: double.infinity,
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(24),
                            ),
                            child: !_loading && _questions.isEmpty
                                ? const Center(
                                    child: Text(
                                      'No questions found for selected filters.',
                                      textAlign: TextAlign.center,
                                    ),
                                  )
                                : Padding(
                                    padding: const EdgeInsets.all(16),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Wrap(
                                          spacing: 8,
                                          runSpacing: 8,
                                          crossAxisAlignment: WrapCrossAlignment.center,
                                          children: [
                                            Container(
                                              padding: const EdgeInsets.symmetric(
                                                horizontal: 10,
                                                vertical: 6,
                                              ),
                                              decoration: BoxDecoration(
                                                color: const Color(0xffEFE6FF),
                                                borderRadius: BorderRadius.circular(18),
                                              ),
                                              child: Text(
                                                'Q ${(current['question_no'] ?? '').toString()}',
                                                style: const TextStyle(
                                                  fontWeight: FontWeight.w700,
                                                  color: Color(0xff5C3B7E),
                                                ),
                                              ),
                                            ),
                                            if (current['year'] != null)
                                              Container(
                                                padding: const EdgeInsets.symmetric(
                                                  horizontal: 10,
                                                  vertical: 6,
                                                ),
                                                decoration: BoxDecoration(
                                                  color: const Color(0xffE8F8F1),
                                                  borderRadius: BorderRadius.circular(18),
                                                ),
                                                child: Text(
                                                  current['year'].toString(),
                                                  style: const TextStyle(
                                                    fontWeight: FontWeight.w700,
                                                    color: Color(0xff236A4F),
                                                  ),
                                                ),
                                              ),
                                            if (_nonEmpty(current['exam']))
                                              Container(
                                                padding: const EdgeInsets.symmetric(
                                                  horizontal: 10,
                                                  vertical: 6,
                                                ),
                                                decoration: BoxDecoration(
                                                  color: const Color(0xffFFF3E0),
                                                  borderRadius: BorderRadius.circular(18),
                                                ),
                                                child: Text(
                                                  current['exam'].toString(),
                                                  style: const TextStyle(
                                                    fontWeight: FontWeight.w600,
                                                    color: Color(0xff8D5A00),
                                                  ),
                                                ),
                                              ),
                                            if (_nonEmpty(current['topic']))
                                              Container(
                                                padding: const EdgeInsets.symmetric(
                                                  horizontal: 10,
                                                  vertical: 6,
                                                ),
                                                decoration: BoxDecoration(
                                                  color: const Color(0xffE3F2FD),
                                                  borderRadius: BorderRadius.circular(18),
                                                ),
                                                child: Text(
                                                  current['topic'].toString(),
                                                  style: const TextStyle(
                                                    fontWeight: FontWeight.w600,
                                                    color: Color(0xff1565C0),
                                                  ),
                                                ),
                                              ),
                                            Text(
                                              '${((_currentPage - 1) * _limit) + _questionIndex + 1} / $_total',
                                              style: const TextStyle(
                                                fontWeight: FontWeight.w600,
                                                color: Color(0xff777777),
                                              ),
                                            ),
                                          ],
                                        ),
                                        const SizedBox(height: 14),
                                        Expanded(
                                          child: SingleChildScrollView(
                                            child: Column(
                                              crossAxisAlignment: CrossAxisAlignment.start,
                                              children: [
                                                ..._buildQuestionBlocks(current),
                                                const SizedBox(height: 14),
                                                ..._buildOptionTiles(current),
                                                if (_nonEmpty(current['correct_answer']) ||
                                                    _nonEmpty(current['answer_display']) ||
                                                    _nonEmpty(current['answer_key']))
                                                  Container(
                                                    width: double.infinity,
                                                    margin: const EdgeInsets.only(top: 6),
                                                    padding: const EdgeInsets.all(12),
                                                    decoration: BoxDecoration(
                                                      borderRadius: BorderRadius.circular(12),
                                                      color: const Color(0xffEAF7EF),
                                                    ),
                                                    child: Text(
                                                      'Answer: ${_answerLine(current)}',
                                                      style: const TextStyle(
                                                        fontWeight: FontWeight.w700,
                                                        color: Color(0xff1E6A45),
                                                      ),
                                                    ),
                                                  ),
                                                if (_nonEmpty(current['explanation']))
                                                  Container(
                                                    width: double.infinity,
                                                    margin: const EdgeInsets.only(top: 10),
                                                    padding: const EdgeInsets.all(12),
                                                    decoration: BoxDecoration(
                                                      borderRadius: BorderRadius.circular(12),
                                                      color: const Color(0xffF5F5F5),
                                                    ),
                                                    child: Text(
                                                      current['explanation'].toString(),
                                                      style: const TextStyle(
                                                        height: 1.35,
                                                        color: Color(0xff444444),
                                                      ),
                                                    ),
                                                  ),
                                              ],
                                            ),
                                          ),
                                        ),
                                        const SizedBox(height: 10),
                                        Row(
                                          children: [
                                            Expanded(
                                              child: OutlinedButton.icon(
                                                onPressed: _prevQuestion,
                                                icon: const Icon(Icons.chevron_left),
                                                label: const Text('Previous'),
                                              ),
                                            ),
                                            const SizedBox(width: 10),
                                            Expanded(
                                              child: ElevatedButton.icon(
                                                onPressed: _nextQuestion,
                                                icon: const Icon(Icons.chevron_right),
                                                label: const Text('Next'),
                                              ),
                                            ),
                                          ],
                                        ),
                                      ],
                                    ),
                                  ),
                          ),
                        ),
                      ),
                    ],
                  ),
      ),
    );
  }

  bool _nonEmpty(dynamic v) {
    if (v == null) return false;
    return v.toString().trim().isNotEmpty;
  }

  String _answerLine(Map<String, dynamic> q) {
    final ca = q['correct_answer']?.toString().trim();
    if (ca != null && ca.isNotEmpty) return ca;
    final ad = q['answer_display']?.toString().trim();
    if (ad != null && ad.isNotEmpty) return ad;
    return (q['answer_key'] ?? '').toString();
  }

  List<Widget> _buildQuestionBlocks(Map<String, dynamic> q) {
    final ta = (q['question_ta'] ?? '').toString().trim();
    final en = (q['question_en'] ?? '').toString().trim();
    final bio = (q['question_text_bilingual'] ?? '').toString().trim();
    if (ta.isEmpty && en.isEmpty) {
      if (bio.isEmpty) return const [];
      return [
        Text(
          bio,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, height: 1.38),
        ),
      ];
    }
    final out = <Widget>[];
    if (ta.isNotEmpty) {
      out.add(
        const Text(
          'தமிழ்',
          style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xff888888)),
        ),
      );
      out.add(
        Text(ta, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, height: 1.38)),
      );
      if (en.isNotEmpty) out.add(const SizedBox(height: 12));
    }
    if (en.isNotEmpty) {
      out.add(
        const Text(
          'English',
          style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xff888888)),
        ),
      );
      out.add(
        Text(en, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, height: 1.38)),
      );
    }
    return out;
  }

  List<Widget> _buildOptionTiles(Map<String, dynamic> q) {
    const letters = ['A', 'B', 'C', 'D'];
    var oen = (q['options_en'] as List<dynamic>?)?.map((e) => e.toString().trim()).toList() ?? <String>[];
    var ota = (q['options_ta'] as List<dynamic>?)?.map((e) => e.toString().trim()).toList() ?? <String>[];
    while (oen.length < 4) {
      oen = [...oen, ''];
    }
    while (ota.length < 4) {
      ota = [...ota, ''];
    }
    final hasStructured = oen.any((s) => s.isNotEmpty) || ota.any((s) => s.isNotEmpty);
    if (!hasStructured) {
      final raw = q['options'] as List<dynamic>? ?? [];
      return raw
          .map(
            (opt) => Container(
              width: double.infinity,
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xffE4D8FB)),
                color: const Color(0xffFAF7FF),
              ),
              child: Text(opt.toString()),
            ),
          )
          .toList();
    }
    final tiles = <Widget>[];
    for (var i = 0; i < 4; i++) {
      final e = i < oen.length ? oen[i] : '';
      final t = i < ota.length ? ota[i] : '';
      if (e.isEmpty && t.isEmpty) continue;
      final String body;
      if (t.isNotEmpty && e.isNotEmpty && t != e) {
        body = '$t\n$e';
      } else {
        body = t.isNotEmpty ? t : e;
      }
      tiles.add(
        Container(
          width: double.infinity,
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: const Color(0xffE4D8FB)),
            color: const Color(0xffFAF7FF),
          ),
          child: Text.rich(
            TextSpan(
              style: const TextStyle(height: 1.35),
              children: [
                TextSpan(text: '${letters[i]}. ', style: const TextStyle(fontWeight: FontWeight.w800)),
                TextSpan(text: body),
              ],
            ),
          ),
        ),
      );
    }
    return tiles;
  }

  Widget _buildFilters() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.14),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            Expanded(
              child: DropdownButtonHideUnderline(
                child: DropdownButton<int?>(
                  value: _selectedYear,
                  dropdownColor: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  hint: const Text('Year', style: TextStyle(color: Colors.white)),
                  iconEnabledColor: Colors.white,
                  isExpanded: true,
                  selectedItemBuilder: (context) => [
                    const Text('All Years', style: TextStyle(color: Colors.white)),
                    ..._years.map((y) => Text(y.toString(), style: const TextStyle(color: Colors.white))),
                  ],
                  items: [
                    const DropdownMenuItem<int?>(
                      value: null,
                      child: Text('All Years'),
                    ),
                    ..._years.map(
                      (y) => DropdownMenuItem<int?>(
                        value: y,
                        child: Text(y.toString()),
                      ),
                    ),
                  ],
                  onChanged: (value) => _applyFilters(year: value, topic: _selectedTopic),
                ),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: DropdownButtonHideUnderline(
                child: DropdownButton<String?>(
                  value: _selectedTopic,
                  dropdownColor: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  hint: const Text('Topic', style: TextStyle(color: Colors.white)),
                  iconEnabledColor: Colors.white,
                  isExpanded: true,
                  selectedItemBuilder: (context) => [
                    const Text('All topics', style: TextStyle(color: Colors.white)),
                    ..._topics.map((s) => Text(s, style: const TextStyle(color: Colors.white))),
                  ],
                  items: [
                    const DropdownMenuItem<String?>(
                      value: null,
                      child: Text('All topics'),
                    ),
                    ..._topics.map(
                      (s) => DropdownMenuItem<String?>(
                        value: s,
                        child: Text(s),
                      ),
                    ),
                  ],
                  onChanged: (value) => _applyFilters(year: _selectedYear, topic: value),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
