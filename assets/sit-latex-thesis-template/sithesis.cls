% sithesis.cls -- 上海应用技术大学本科毕业设计（论文）LaTeX 模板（草案）
% 编译方式：XeLaTeX 或 LuaLaTeX。不要用 pdfLaTeX。
% 本模板根据用户上传的《毕业设计论文编写格式要求规范（2024更新）》示例整理。
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{sithesis}[2026/05/15 Shanghai Institute of Technology undergraduate thesis template]

\RequirePackage{iftex}
\ifXeTeX\else
  \ifLuaTeX\else
    \ClassError{sithesis}{请使用 XeLaTeX 或 LuaLaTeX 编译}{本模板需要 fontspec/xeCJK 处理中文字体。}
  \fi
\fi

% fontset=fandol：不依赖系统自带华文/苹方路径；新版 macOS 上 ctex 的 mac 探测可能误判为 macold 导致缺字。
\LoadClass[UTF8,twoside,zihao=-4,fontset=fandol]{ctexart}

\RequirePackage{fontspec}
\RequirePackage{ifplatform}
\RequirePackage{geometry}
\RequirePackage{setspace}
\RequirePackage{graphicx}
\RequirePackage{xcolor}
\RequirePackage{amsmath,amssymb,mathtools}
\RequirePackage{booktabs,longtable,tabularx,array,multirow,makecell,threeparttable}
\RequirePackage{caption}
\RequirePackage{fancyhdr}
\RequirePackage{titletoc}
\RequirePackage{etoolbox}
\RequirePackage{cite}
\RequirePackage{hyperref}

% ---------------------------
% 页面与基础排版
% ---------------------------
% 上传的格式文件未明确给出页边距；这里采用 A4 和常见论文边距。
% 如学院另有精确数值，请改此处。
\geometry{
  a4paper,
  left=2.6cm,
  right=2.6cm,
  top=2.5cm,
  bottom=2.5cm,
  headheight=15pt,
  headsep=0.8cm,
  footskip=1.2cm
}

\setlength{\parindent}{2em}
\setlength{\parskip}{0pt}
\setstretch{1.25}
\raggedbottom
\setlength{\emergencystretch}{2em}

% ---------------------------
% 字体设置
% ---------------------------
% 按要求：中文宋体，非汉字/数字/字母 Times New Roman。
% Windows 上优先使用 SimSun/SimHei；macOS 上优先使用系统宋体/黑体，避免 Fandol CID 字体在部分 PDF 查看器中中文不显示。
% macOS 上 \IfFontExistsTF{SimSun} 可能对“幽灵字体名”为真，导致 XeLaTeX 无法真正加载，故 SimSun 链仅在 \ifwindows 下尝试。
\newcommand{\sit@setfonts}{%
  \IfFontExistsTF{Times New Roman}{%
    \setmainfont{Times New Roman}%
  }{%
    \IfFontExistsTF{TeX Gyre Termes}{\setmainfont{TeX Gyre Termes}}{\setmainfont{Latin Modern Roman}}%
  }%
  \ifwindows
    \IfFontExistsTF{SimSun}{%
      \setCJKmainfont{SimSun}[AutoFakeBold=true,AutoFakeSlant=true]%
    }{%
      \IfFontExistsTF{Noto Serif CJK SC}{%
        \setCJKmainfont{Noto Serif CJK SC}%
      }{%
        \IfFontExistsTF{Source Han Serif SC}{%
          \setCJKmainfont{Source Han Serif SC}%
        }{%
          \setCJKmainfont{FandolSong-Regular}[
            Extension = .otf,
            BoldFont = FandolSong-Bold,
            ItalicFont = FandolKai-Regular
          ]%
        }%
      }%
    }%
    \IfFontExistsTF{SimHei}{%
      \setCJKsansfont{SimHei}[AutoFakeBold=true]%
    }{%
      \IfFontExistsTF{Noto Sans CJK SC}{%
        \setCJKsansfont{Noto Sans CJK SC}%
      }{%
        \IfFontExistsTF{Source Han Sans SC}{%
          \setCJKsansfont{Source Han Sans SC}%
        }{%
          \setCJKsansfont{FandolHei-Regular}[Extension = .otf, BoldFont = FandolHei-Bold]%
        }%
      }%
    }%
    \IfFontExistsTF{FangSong}{%
      \setCJKmonofont{FangSong}%
    }{%
      \setCJKmonofont{FandolFang-Regular}[Extension = .otf]%
    }%
  \else
    \IfFontExistsTF{Songti SC}{%
      \setCJKmainfont{Songti SC}[AutoFakeSlant=true]%
      \setCJKfamilyfont{zhsong}{Songti SC}[AutoFakeSlant=true]%
      \setCJKfamilyfont{zhfs}{Songti SC}[AutoFakeSlant=true]%
      \setCJKfamilyfont{zhkai}{Songti SC}[AutoFakeSlant=true]%
    }{%
      \IfFontExistsTF{Noto Serif CJK SC}{%
        \setCJKmainfont{Noto Serif CJK SC}%
        \setCJKfamilyfont{zhsong}{Noto Serif CJK SC}%
        \setCJKfamilyfont{zhfs}{Noto Serif CJK SC}%
        \setCJKfamilyfont{zhkai}{Noto Serif CJK SC}%
      }{%
        \IfFontExistsTF{Source Han Serif SC}{%
          \setCJKmainfont{Source Han Serif SC}%
          \setCJKfamilyfont{zhsong}{Source Han Serif SC}%
          \setCJKfamilyfont{zhfs}{Source Han Serif SC}%
          \setCJKfamilyfont{zhkai}{Source Han Serif SC}%
        }{%
        }%
      }%
    }%
    \IfFontExistsTF{Heiti SC}{%
      \setCJKsansfont{Heiti SC}[AutoFakeBold=true]%
      \setCJKfamilyfont{zhhei}{Heiti SC}[AutoFakeBold=true]%
    }{%
      \IfFontExistsTF{Noto Sans CJK SC}{%
        \setCJKsansfont{Noto Sans CJK SC}%
        \setCJKfamilyfont{zhhei}{Noto Sans CJK SC}%
      }{%
        \IfFontExistsTF{Source Han Sans SC}{%
          \setCJKsansfont{Source Han Sans SC}%
          \setCJKfamilyfont{zhhei}{Source Han Sans SC}%
        }{%
        }%
      }%
    }%
  \fi
}
\sit@setfonts

% 中文字号：正文小四；表格/图中字体五号。
\AtBeginDocument{\zihao{-4}\songti\setstretch{1.25}}

% ---------------------------
% 元数据命令
% ---------------------------
\makeatletter

% 双面打印：所有结构性起始页使用 \cleardoublepage，必要时自动补空白页，
% 确保目录、正文起始、致谢/参考文献等从奇数页（右页）开始；普通章节只另起新页。
\def\cleardoublepage{%
  \clearpage
  \if@twoside
    \ifodd\c@page
    \else
      \thispagestyle{empty}\hbox{}\newpage
      \if@twocolumn\thispagestyle{empty}\hbox{}\newpage\fi
    \fi
  \fi
}
\newcommand{\sit@title}{毕业设计（论文）题目}
\newcommand{\sit@shorttitle}{毕业设计（论文）题目}
\newcommand{\sit@englishtitle}{Language Learning}
\newcommand{\sit@college}{}
\newcommand{\sit@major}{}
\newcommand{\sit@classid}{}
\newcommand{\sit@studentid}{}
\newcommand{\sit@studentname}{}
\newcommand{\sit@supervisor}{}
\newcommand{\sit@period}{}
\newcommand{\sit@logofile}{figures/sit-logo.pdf}
\newcommand{\sit@thesistype}{本科毕业设计(论文)}

\newcommand{\thesistitle}[1]{\gdef\sit@title{#1}\gdef\sit@shorttitle{#1}\title{#1}\hypersetup{pdftitle={#1}}}
\newcommand{\shorttitle}[1]{\gdef\sit@shorttitle{#1}}
\newcommand{\englishtitle}[1]{\gdef\sit@englishtitle{#1}}
\newcommand{\college}[1]{\gdef\sit@college{#1}}
\newcommand{\major}[1]{\gdef\sit@major{#1}}
\newcommand{\classid}[1]{\gdef\sit@classid{#1}}
\newcommand{\studentid}[1]{\gdef\sit@studentid{#1}}
\newcommand{\studentname}[1]{\gdef\sit@studentname{#1}}
\newcommand{\supervisor}[1]{\gdef\sit@supervisor{#1}}
\newcommand{\period}[1]{\gdef\sit@period{#1}}
\newcommand{\universitylogo}[1]{\gdef\sit@logofile{#1}}
\newcommand{\thesistype}[1]{\gdef\sit@thesistype{#1}}

% ---------------------------
% 页眉页脚
% ---------------------------
\newcommand{\sit@pagenumformat}[1]{\zihao{5}—~#1~—}
\renewcommand{\@cite}[2]{\textsuperscript{[#1\if@tempswa, #2\fi]}}

\fancypagestyle{sitfront}{%
  \fancyhf{}%
  \renewcommand{\headrulewidth}{0pt}%
  \renewcommand{\footrulewidth}{0pt}%
  % 按用户确认：模板说明写反了；页码奇数页在右侧，偶数页在左侧。
  \fancyfoot[RO]{\sit@pagenumformat{\thepage}}%
  \fancyfoot[LE]{\sit@pagenumformat{\thepage}}%
}

\fancypagestyle{sitmain}{%
  \fancyhf{}%
  \renewcommand{\headrulewidth}{0.4pt}%
  \renewcommand{\footrulewidth}{0pt}%
  % 按要求：页眉从正文开始，文章标题居中。
  \fancyhead[C]{\zihao{5}\songti\sit@shorttitle}%
  \fancyfoot[RO]{\sit@pagenumformat{\thepage}}%
  \fancyfoot[LE]{\sit@pagenumformat{\thepage}}%
}

% ---------------------------
% 章节标题：一级小二黑体，二级四号黑体，三级小四黑体；
% 编号后留一个英文字符，标题末尾不加标点。
% ---------------------------
\ctexset{
  section = {
    format = {\raggedright\heiti\bfseries\zihao{-2}},
    name = {},
    number = {\arabic{section}},
    aftername = {\quad},
    beforeskip = {1\baselineskip},
    afterskip = {1\baselineskip}
  },
  subsection = {
    format = {\raggedright\heiti\zihao{4}},
    name = {},
    number = {\thesection.\arabic{subsection}},
    aftername = {\quad},
    beforeskip = {1\baselineskip},
    afterskip = {0pt}
  },
  subsubsection = {
    format = {\raggedright\heiti\zihao{-4}},
    name = {},
    number = {\thesubsection.\arabic{subsubsection}},
    aftername = {\quad},
    beforeskip = {1\baselineskip},
    afterskip = {0pt}
  }
}

\setcounter{secnumdepth}{3}
\setcounter{tocdepth}{3}

% 每个一级标题另起新页。
\newif\ifsit@mainmatter
\sit@mainmatterfalse
\pretocmd{\section}{\ifsit@mainmatter\ifnum\value{section}>0\clearpage\fi\fi}{}{}

% ---------------------------
% 目录样式：一、二、三级标题；一级加粗左对齐；二/三级分别缩进；点线连接页码。
% ---------------------------
\renewcommand{\contentsname}{目\quad 录}
\titlecontents{section}
  [0em]
  {\zihao{-4}\songti\bfseries}
  {\contentslabel{2.2em}}
  {}
  {\titlerule*[0.5pc]{.}\contentspage}
\titlecontents{subsection}
  [1em]
  {\zihao{-4}\songti}
  {\contentslabel{3.0em}}
  {}
  {\titlerule*[0.5pc]{.}\contentspage}
\titlecontents{subsubsection}
  [2em]
  {\zihao{-4}\songti}
  {\contentslabel{4.0em}}
  {}
  {\titlerule*[0.5pc]{.}\contentspage}

\newcommand{\maketableofcontents}{%
  \cleardoublepage
  \phantomsection
  \thispagestyle{sitfront}%
  \begin{center}
    {\zihao{-2}\heiti\bfseries 目\quad 录}
  \end{center}
  \vspace{1\baselineskip}
  \@starttoc{toc}%
  \cleardoublepage
}

% ---------------------------
% 公式、图、表编号：1.1、1.2 等。
% ---------------------------
\numberwithin{equation}{section}
\numberwithin{figure}{section}
\numberwithin{table}{section}

% 图题在下，表题在上；题名黑体五号，表序/图序后空一字符。
\DeclareCaptionFont{sitcaption}{\zihao{5}\heiti}
\captionsetup{
  font = sitcaption,
  labelfont = sitcaption,
  labelsep = quad,
  justification = centering,
  singlelinecheck = true
}
\captionsetup[figure]{name=图, position=bottom}
\captionsetup[table]{name=表, position=top}
\captionsetup[longtable]{singlelinecheck=false, justification=centering}
\setlength{\LTcapwidth}{\textwidth}

% 正文中表格与插图的字体一律用 5 号宋体。
\AtBeginEnvironment{tabular}{\zihao{5}\songti}
\AtBeginEnvironment{tabularx}{\zihao{5}\songti}
\AtBeginEnvironment{longtable}{\zihao{5}\songti}
\AtBeginEnvironment{threeparttable}{\zihao{5}\songti}
\renewcommand{\arraystretch}{1.25}

% ---------------------------
% 封面
% ---------------------------
\newcommand{\sit@coverlabel}[1]{\makebox[4em][s]{#1}}
\newcommand{\sit@coverline}[2]{%
  \noindent{\zihao{3}\heiti\sit@coverlabel{#1}}\quad
  \underline{\makebox[10.5cm][c]{\zihao{3}\songti #2}}\par\vspace{1.1cm}%
}

\newcommand{\makecover}{%
  \begin{titlepage}
    \thispagestyle{empty}%
    \vspace*{0.2cm}
    \begin{center}
      \IfFileExists{\sit@logofile}{%
        \includegraphics[width=0.62\textwidth]{\sit@logofile}%
      }{%
        {\zihao{1}\heiti 上海应用技术大学}\par
        \vspace{0.2cm}
        {\zihao{4}SHANGHAI INSTITUTE OF TECHNOLOGY}%
      }%
      \vspace{1.6cm}

      {\zihao{0}\heiti\sit@thesistype}\par
    \end{center}

    \vspace{1.8cm}
    \noindent{\zihao{2}\heiti 课题名称:}\quad
    \underline{\makebox[10.7cm][c]{\zihao{3}\songti\sit@title}}\par

    \vspace{2.1cm}
    \sit@coverline{学 院}{\sit@college}
    \sit@coverline{专 业}{\sit@major}

    \noindent{\zihao{3}\heiti\sit@coverlabel{班 级}}\quad
    \underline{\makebox[4.0cm][c]{\zihao{3}\songti\sit@classid}}\quad
    {\zihao{3}\heiti 学号}\quad
    \underline{\makebox[4.0cm][c]{\zihao{3}\songti\sit@studentid}}\par\vspace{1.1cm}

    \sit@coverline{学生姓名}{\sit@studentname}
    \sit@coverline{指导教师}{\sit@supervisor}
    \sit@coverline{起止日期}{\sit@period}
    \vfill
  \end{titlepage}
  \cleardoublepage
}

% ---------------------------
% 前置部分与正文部分
% ---------------------------
\newcommand{\frontmatter}{%
  \cleardoublepage
  \sit@mainmatterfalse
  \pagenumbering{Roman}%
  \setcounter{page}{1}%
  \pagestyle{sitfront}%
}

\newcommand{\mainmatter}{%
  \cleardoublepage
  \sit@mainmattertrue
  \pagenumbering{arabic}%
  \setcounter{page}{1}%
  \pagestyle{sitmain}%
}

% ---------------------------
% 独创性声明
% ---------------------------
\newcommand{\makedeclaration}{%
  \cleardoublepage
  \thispagestyle{sitfront}%
  \begin{center}
    {\zihao{3}\heiti 毕业设计（论文）独创性声明}
  \end{center}
  \vspace{1.5\baselineskip}
  {\zihao{-4}\songti
  本人所呈交的毕业论文是在指导教师指导下进行的工作及取得的成果。除文中已经注明的内容外，本论文不包含其他个人已经发表或撰写过的研究成果。对本文的研究做出重要贡献的个人和集体，均已在文中作了明确说明并表示谢意。

  \vspace{6\baselineskip}
  \begin{flushright}
    作者签名：\makebox[4.0cm][l]{}\par
    \vspace{0.8\baselineskip}
    日\quad 期：\makebox[4.0cm][l]{}\par
  \end{flushright}}
  \cleardoublepage
}

% ---------------------------
% 中英文摘要
% ---------------------------
\newenvironment{cnabstract}{%
  \cleardoublepage
  \thispagestyle{sitfront}%
  \begin{center}
    {\zihao{-2}\heiti\bfseries \sit@title}
  \end{center}
  \vspace{1\baselineskip}
  \zihao{-4}\setstretch{1.25}\noindent{\heiti\bfseries 摘要：}\songti
}{\par}

\newcommand{\cnkeywords}[1]{%
  \par\vspace{1\baselineskip}
  \noindent{\heiti\bfseries 关键词：}\songti\hspace{1em}#1\par
}

\newenvironment{enabstract}{%
  \vspace{2\baselineskip}
  \begin{center}
    {\zihao{-2}\bfseries \sit@englishtitle}
  \end{center}
  \vspace{1\baselineskip}
  \zihao{-4}\setstretch{1.25}\noindent{\bfseries Abstract: }\rmfamily
}{\par}

\newcommand{\enkeywords}[1]{%
  \par\vspace{1\baselineskip}
  \noindent{\bfseries KeyWords:}\rmfamily\hspace{1em}#1\par\cleardoublepage
}

% ---------------------------
% 正文中的“（1） 标题”类条目，编号后留一个英文空格。
% ---------------------------
\newcounter{sititemtitle}
\newcommand{\resetsubitemtitle}{\setcounter{sititemtitle}{0}}
\newcommand{\subitemtitle}[1]{%
  \refstepcounter{sititemtitle}%
  \par\vspace{1\baselineskip}\noindent\hspace*{2em}{\songti\zihao{-4}（\arabic{sititemtitle}）~#1}\par%
}

% ---------------------------
% 致谢、参考文献、附录
% ---------------------------
\newenvironment{acknowledgements}{%
  \cleardoublepage
  \phantomsection
  \addcontentsline{toc}{section}{致\quad 谢}%
  {\centering\zihao{-2}\heiti\bfseries 致\quad 谢\par}
  \vspace{1\baselineskip}
  \zihao{-4}\songti\setlength{\parindent}{2em}%
}{\par}

\renewcommand{\refname}{参考文献}
\renewenvironment{thebibliography}[1]{%
  \cleardoublepage
  \phantomsection
  \addcontentsline{toc}{section}{参考文献}%
  \begin{center}{\zihao{-2}\heiti\bfseries 参考文献}\end{center}
  \vspace{1\baselineskip}
  \zihao{-4}\songti\setstretch{1.25}%
  \list{\@biblabel{\@arabic\c@enumiv}}{%
    \settowidth\labelwidth{\@biblabel{#1}}%
    \leftmargin\labelwidth
    \advance\leftmargin\labelsep
    \setlength{\itemsep}{0pt}%
    \setlength{\parsep}{0pt}%
    \usecounter{enumiv}%
    \let\p@enumiv\@empty
    \renewcommand\theenumiv{\@arabic\c@enumiv}%
  }%
  \sloppy\clubpenalty4000\widowpenalty4000\sfcode`\.=\@m
}{%
  \def\@noitemerr{\@latex@warning{Empty `thebibliography' environment}}%
  \endlist
}

\newenvironment{appendixmaterial}{%
  \cleardoublepage
  \phantomsection
  \addcontentsline{toc}{section}{附\quad 录}%
  \begin{center}{\zihao{-2}\heiti\bfseries 附\quad 录}\end{center}
  \vspace{1\baselineskip}
  \zihao{-4}\songti
}{\par}

% 超链接样式
\hypersetup{
  hidelinks,
  pdfauthor = {Shanghai Institute of Technology},
  pdftitle = {\sit@title}
}
\makeatother
