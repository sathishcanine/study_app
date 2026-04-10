// ignore_for_file: must_be_immutable

import 'package:audioplayers/audioplayers.dart';
import 'package:study_app/services/auth_storage.dart';
import 'package:flutter/material.dart';
import 'package:page_transition/page_transition.dart';
import 'package:study_app/constants.dart';
import 'package:study_app/helper/showcaseview.dart';
import 'package:study_app/pages/details_page.dart';
import 'package:study_app/pages/leader_board_page.dart';
import 'package:study_app/pages/login_page.dart';
import 'package:study_app/pages/profile_page.dart';
import 'package:study_app/pages/homePage_tabs/first_tab.dart';
import 'package:study_app/pages/homePage_tabs/secound_tab.dart';
import 'package:study_app/pages/homePage_tabs/third_tab.dart';
import 'package:study_app/widgets/custom_searchbar.dart';
import 'package:study_app/widgets/drawer_list_tile.dart';
import 'package:showcaseview/showcaseview.dart';

class HomePageWidget extends StatefulWidget {
  const HomePageWidget({
    super.key,
    required this.username,
    required this.email,
    required this.score,
    required this.data,
    this.first = false,
  });

  final String? username, email;
  static String id = "/homePageWidget";
  final int score;
  final Map<String, dynamic> data;
  final bool first;

  @override
  State<HomePageWidget> createState() => _HomePageWidgetState();
}

class _HomePageWidgetState extends State<HomePageWidget> {
  final AudioPlayer player = AudioPlayer();
  final GlobalKey globalKeyOne = GlobalKey();
  final GlobalKey globalKeyTwo = GlobalKey();
  final GlobalKey globalKeyThree = GlobalKey();
  final GlobalKey globalKeyFour = GlobalKey();
  final GlobalKey globalKeyFive = GlobalKey();
  int _selectedBottomIndex = 0;

  @override
  void initState() {
    if (widget.first) {
      WidgetsBinding.instance.addPostFrameCallback(
        (timeStamp) => ShowCaseWidget.of(context).startShowCase(
          [
            globalKeyOne,
            globalKeyTwo,
            globalKeyThree,
            globalKeyFour,
            globalKeyFive,
          ],
        ),
      );
    }

    super.initState();
  }

  void updateIndex(int index, int? id) {
    // No-op for now, subject cards navigate directly to sets page.
  }

  @override
  Widget build(BuildContext context) {
    final bottomItems = <_BottomMenuItem>[
      const _BottomMenuItem(label: "Test", icon: Icons.quiz_outlined),
      const _BottomMenuItem(label: "PYQ", icon: Icons.history_edu_outlined),
      const _BottomMenuItem(label: "Ai Home", icon: Icons.auto_awesome_outlined),
      const _BottomMenuItem(
        label: "Current",
        icon: Icons.newspaper_outlined,
      ),
      const _BottomMenuItem(label: "Mains", icon: Icons.menu_book_outlined),
    ];

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
      child: Scaffold(
        resizeToAvoidBottomInset: false,
        drawer: SafeArea(
          child: Drawer(
            child: ListView(
              children: [
                DrawerHeader(
                  decoration: const BoxDecoration(
                    color: Color(0xffA166DC),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Image.asset(
                        "assets/images/man.png",
                        width: 74,
                        height: 74,
                      ),
                      const SizedBox(
                        height: 5,
                      ),
                      Text(
                        widget.username!,
                        style: TextStyle(
                          color: Colors.white,
                          fontFamily: kFontText,
                          fontSize: 21,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      Text(
                        " ${widget.score} points",
                        style: TextStyle(
                          fontSize: 12.7,
                          fontWeight: FontWeight.w300,
                          fontFamily: kFontText,
                          color: Colors.white,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(
                  height: 45,
                ),
                DrawerListTile(
                  onTap: () {},
                  icon: Icons.home,
                  title: "Home",
                ),
                const SizedBox(
                  height: 15,
                ),
                DrawerListTile(
                  onTap: () {
                    Navigator.of(context).push(
                      PageTransition(
                        child: AddPage(email: widget.email!),
                        type: PageTransitionType.rightToLeft,
                        duration: const Duration(milliseconds: 300),
                        reverseDuration: const Duration(milliseconds: 300),
                      ),
                    );
                  },
                  icon: Icons.help_outline,
                  title: "Game Guide",
                ),
                const SizedBox(
                  height: 15,
                ),
                DrawerListTile(
                  onTap: () {
                    Navigator.pop(context);
                    Navigator.push(
                      context,
                      PageTransition(
                        child: ProfilePage(email: widget.email!, data: widget.data),
                        type: PageTransitionType.rightToLeft,
                        duration: const Duration(milliseconds: 300),
                      ),
                    );
                  },
                  icon: Icons.person_outline,
                  title: "Account",
                ),
                const SizedBox(
                  height: 15,
                ),
                DrawerListTile(
                  onTap: () {
                    Navigator.push(
                      context,
                      PageTransition(
                        child: LeaderBoardPage(email: widget.email!),
                        type: PageTransitionType.rightToLeft,
                        duration: const Duration(milliseconds: 300),
                      ),
                    );
                  },
                  icon: Icons.emoji_events_outlined,
                  title: "Leaderboard",
                ),
                const SizedBox(
                  height: 15,
                ),
                DrawerListTile(
                  onTap: () async {
                    await AuthStorage.clear();
                    if (context.mounted) {
                      Navigator.popAndPushNamed(context, LogInPage.id);
                    }
                  },
                  icon: Icons.logout,
                  title: "Logout",
                ),
              ],
            ),
          ),
        ),
        backgroundColor: Colors.transparent,
        appBar: AppBar(
          automaticallyImplyLeading: false,
          clipBehavior: Clip.none,
          backgroundColor: Colors.transparent,
          title: Row(
            children: [
              Builder(
                builder: (context) => ShowCaseView(
                  globalKey: globalKeyOne,
                  title: "Explore Navigation Options",
                  description:
                      "Access different sections and features through the navigation menu.",
                  child: IconButton(
                    onPressed: () {
                      Scaffold.of(context).openDrawer();
                    },
                    icon: const Icon(
                      Icons.menu,
                      size: 30,
                      color: Colors.white,
                    ),
                  ),
                ),
              ),
            ],
          ),
          actions: [
            GestureDetector(
              onTap: () {
                Navigator.push(
                  context,
                  PageTransition(
                    child: ProfilePage(email: widget.email!, data: widget.data),
                    type: PageTransitionType.size,
                    alignment: Alignment.center,
                    duration: const Duration(milliseconds: 500),
                    reverseDuration: const Duration(milliseconds: 500),
                  ),
                );
              },
              child: ShowCaseView(
                globalKey: globalKeyTwo,
                title: "Your Personal Space",
                description:
                    "Discover stats, game history, and profile details effortlessly. Dive into insights, review game history, and manage profile settings.",
                child: Image.asset("assets/images/man.png"),
              ),
            ),
            const SizedBox(
              width: 15,
            )
          ],
        ),
        body: Stack(
          children: [
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 350),
              switchInCurve: Curves.easeOutBack,
              switchOutCurve: Curves.easeIn,
              child: _selectedBottomIndex == 0
                  ? _buildTestHomeBody()
                  : _MenuPlaceholderPage(
                      key: ValueKey<int>(_selectedBottomIndex),
                      title: bottomItems[_selectedBottomIndex].label,
                      subtitle: "This section is ready for your content.",
                      icon: bottomItems[_selectedBottomIndex].icon,
                    ),
            ),
            Positioned(
              left: 14,
              right: 14,
              bottom: 14,
              child: _FloatingBottomBar(
                items: bottomItems,
                selectedIndex: _selectedBottomIndex,
                onTap: (index) {
                  setState(() {
                    _selectedBottomIndex = index;
                  });
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTestHomeBody() {
    return DefaultTabController(
      key: const ValueKey<int>(0),
      length: 3,
      child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 36),
                  child: Text(
                    "Hello, ${widget.username} ",
                    style: const TextStyle(
                      fontSize: 15,
                      fontFamily: 'DM Sans',
                      color: Colors.white,
                    ),
                  ),
                ),
                const SizedBox(
                  height: 5,
                ),
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 36),
                  child: Text(
                    "Let's test your knowledge",
                    style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                      fontFamily: "Ubuntu",
                    ),
                  ),
                ),
                const SizedBox(
                  height: 10,
                ),
                ShowCaseView(
                  globalKey: globalKeyThree,
                  title: "Quick Category Search",
                  description:
                      "Easily find specific categories by typing keywords into the search bar.",
                  child: CustomSearchBar(
                    email: widget.email!,
                  ),
                ),
                const SizedBox(
                  height: 10,
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(
                      right: 12,
                      left: 12,
                      top: 10,
                      bottom: 92,
                    ),
                    child: Container(
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(32),
                      ),
                      child: Column(
                        children: [
                          Container(
                            margin: const EdgeInsets.only(
                              top: 20,
                              bottom: 10,
                            ),
                            width: 55,
                            height: 4,
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(10),
                              gradient: LinearGradient(
                                colors: [
                                  kPrimaryColor,
                                  const Color(0xff5C3B7E),
                                ],
                              ),
                            ),
                          ),
                          const TabBar(
                            labelPadding: EdgeInsets.all(1),
                            dividerColor: Colors.transparent,
                            padding: EdgeInsets.symmetric(horizontal: 10),
                            labelStyle:
                                TextStyle(fontFamily: "Nunito", fontSize: 15),
                            tabs: [
                              Tab(
                                text: "Popular",
                              ),
                              Tab(
                                text: "Entertainment",
                              ),
                              Tab(
                                text: "Science",
                              ),
                            ],
                          ),
                          Expanded(
                            child: TabBarView(
                              children: [
                                ShowCaseView(
                                  globalKey: globalKeyFour,
                                  title: "Explore Topic Categories",
                                  description:
                                      "Select a category to delve into quizzes related to specific subjects.",
                                  child: FirstTab(
                                    updateIndex: updateIndex,
                                    email: widget.email!,
                                  ),
                                ),
                                SecoundTab(
                                  updateIndex: updateIndex,
                                ),
                                ThirdTab(
                                  updateIndex: updateIndex,
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 15),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
    );
  }
}

class _BottomMenuItem {
  const _BottomMenuItem({
    required this.label,
    required this.icon,
  });
  final String label;
  final IconData icon;
}

class _FloatingBottomBar extends StatelessWidget {
  const _FloatingBottomBar({
    required this.items,
    required this.selectedIndex,
    required this.onTap,
  });

  final List<_BottomMenuItem> items;
  final int selectedIndex;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.95),
        borderRadius: BorderRadius.circular(30),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.12),
            blurRadius: 20,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Row(
        children: List.generate(items.length, (index) {
          final isSelected = selectedIndex == index;
          return Expanded(
            child: GestureDetector(
              onTap: () => onTap(index),
              behavior: HitTestBehavior.opaque,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 260),
                curve: Curves.easeOutCubic,
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
                decoration: BoxDecoration(
                  gradient: isSelected
                      ? LinearGradient(
                          colors: [kPrimaryColor, const Color(0xff5C3B7E)],
                        )
                      : null,
                  borderRadius: BorderRadius.circular(22),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    AnimatedScale(
                      duration: const Duration(milliseconds: 220),
                      scale: isSelected ? 1.12 : 1.0,
                      child: Icon(
                        items[index].icon,
                        size: 20,
                        color: isSelected ? Colors.white : const Color(0xff7A7A7A),
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      items[index].label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: isSelected ? Colors.white : const Color(0xff7A7A7A),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        }),
      ),
    );
  }
}

class _MenuPlaceholderPage extends StatelessWidget {
  const _MenuPlaceholderPage({
    super.key,
    required this.title,
    required this.subtitle,
    required this.icon,
  });

  final String title;
  final String subtitle;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Center(
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 28),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(28),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircleAvatar(
                radius: 34,
                backgroundColor: const Color(0xffA166DC).withOpacity(0.12),
                child: Icon(
                  icon,
                  color: const Color(0xffA166DC),
                  size: 34,
                ),
              ),
              const SizedBox(height: 14),
              Text(
                title,
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                  fontFamily: "Ubuntu",
                ),
              ),
              const SizedBox(height: 8),
              Text(
                subtitle,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: 14,
                  color: Color(0xff666666),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
