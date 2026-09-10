/* ══════════════════════════════════════════════════════════════════════
   kit-config.example.js — 網站設定的「範本」
   ──────────────────────────────────────────────────────────────────────
   實際使用的 site/js/kit-config.js **不要手寫**：
   由 scripts/build_config.py 讀 config/kit.json ＋ config/tabs.json 產生
   （產生檔已被 .gitignore 擋住）。本檔只是形狀範例與預設文案來源。

   本檔用傳統的 script 標籤載入（不是 module），
   載完之後全域只多一個 window.KIT。

   真正產生的 kit-config.js 還會多一個 version（版本字串，取自 VERSION 檔），
   網頁頁尾直接顯示它；沒有這個鍵時頁尾會寫「版本未知」。

   ── v3 §3.6：三個高痛點垂直方案 ──────────────────────────────────────
   學生記錄類型庫以三個垂直方案為主幹：
     ① qualitative（質性評量自動化）② iep（IEP／早療追蹤）③ soap（諮商 SOAP）
   每個方案＝「一種記錄類型（含逐欄引導 hint）＋一種期末產出格式」。
   多出來的三個鍵：
     · 每個 field 都有 hint（表單裡欄位下方那一行灰字）
     · 類型可以帶 card：{goals:true}＝學生卡有目標清單；
                        {conceptualization:true}＝學生卡有個案概念化
     · reportFormats［期末一鍵產出的格式庫］、verticals［方案庫，只建議不預勾］
   ══════════════════════════════════════════════════════════════════════ */

window.KIT = {

  // true＝示範模式：完全不連 Firebase，資料只存在這個瀏覽器（localStorage）。
  // 網址加 ?demo=1 也會進示範模式。build_preview.py 產生的單檔預覽固定為 true。
  demo: false,

  // 只有這個 Google 帳號會被當成擁有者（要與 firestore.rules 裡的一致）
  ownerEmail: "you@example.com",

  // 學生代號前綴，不含後面那一槓（代號長這樣：S-01、S-02…；網頁自己補上「-」）。
  // 與 config/kit.example.json 的 id_prefix 一致。想用班級當前綴（5A-01）也可以。
  idPrefix: "S",

  // ── 三個分頁（形狀與 config/tabs.json 完全一致）────────────────────
  tabs: {

    students: {
      enabled: true,

      // ── 這位老師實際勾選的「記錄類型」────────────────────────────
      // 學生記錄不能混在一起：質性評量、IEP、SOAP 各是一種類型，
      // 各有自己的欄位、分類詞與「哪些學生在裡面」。
      // 安裝時由老師從下面的 studentStreamLibrary 勾，**一個都不預設勾**；
      // 這裡列的三種是三個垂直方案的示範（也是單檔預覽的示範資料來源）。
      //   scope: "class" ＝全班每一位學生都在裡面
      //   scope: "case"  ＝只有被列入的學生（名冊 students[].streams 決定）
      streams: [
        {
          id: "qualitative",
          label: "質性評量觀察",
          desc: "不打分數的學校怎麼記：每一則一個具體事件，先標好面向與報告維度，期末就不必重讀一整年。",
          scope: "class",
          fields: [
            { name: "面向", type: "multiselect", options: ["頭·思考", "心·情感", "手·意志", "社群·人際"],
              hint: "這一則主要看見的是哪幾個面向？可以複選。" },
            { name: "報告維度", type: "select",
              options: ["行為與自我管理", "人際互動", "學習態度與能力", "內在特質與個人發展", "挑戰與方向"],
              hint: "期末評語照這五個維度分段；記的時候先標好，期末一鍵就分得出來。" },
            { name: "課程", type: "text", hint: "填課程名或科目" },
            { name: "證據來源", type: "select", options: ["工作本", "課堂觀察", "口說", "身體", "作品", "親師"],
              hint: "這一則是從哪裡看到的？寫得出來源，期末的話才站得住。" },
            { name: "指標", type: "text",
              hint: "「第N條 可獨立完成｜需輔助完成｜尚無法完成；情意類不打等級」" }
          ],
          tags: ["#課堂", "#主課程", "#學習態度", "#專注意志", "#人際", "#情緒", "#突破", "#親師", "#生活"],
          custom: false
        },
        {
          id: "iep",
          label: "IEP 個案追蹤",
          desc: "特教與早療：先在學生卡上列好這學期的目標，每一則記錄對準一個目標，期末每個目標自動出一張表。",
          scope: "case",
          // 學生卡多一張「目標清單」（students/{id}.goals）
          card: { goals: true },
          fields: [
            { name: "目標編號", type: "goal", hint: "從這位學生的目標清單挑一個；還沒有就先在上方「目標清單」加。" },
            { name: "達成情形", type: "select", options: ["未開始", "初步", "部分達成", "達成", "類化"],
              hint: "照這一次實際看到的填，不填期望值。" },
            { name: "證據", type: "select", options: ["觀察", "作品", "測驗", "家長回報"],
              hint: "這個判斷是從哪裡來的？" },
            { name: "支持策略", type: "text", hint: "這一次用了什麼調整或支持（提示、教具、環境、時間）。" },
            { name: "下一步", type: "text", hint: "只寫一個下一步，寫得出來才做得到。" }
          ],
          tags: ["#IEP", "#鑑定", "#資源班", "#巡迴", "#個案會議", "#轉銜", "#早療"],
          custom: false
        },
        {
          id: "soap",
          label: "諮商／個案 SOAP 紀錄",
          desc: "會談完照 S／O／A／P 四段拆，個案卡上放個案概念化，期末或結案一鍵出摘要。",
          scope: "case",
          // 舊資料相容：v2 的 counseling 併進 soap，讀得到舊紀錄
          aliases: ["counseling"],
          // 學生卡多一張「個案概念化」（students/{id}.conceptualization）
          card: { conceptualization: true },
          fields: [
            { name: "S 主觀", type: "text", hint: "個案自己說的話與主觀感受" },
            { name: "O 客觀", type: "text", hint: "可觀察的行為與事實" },
            { name: "A 評估", type: "text", hint: "專業評估與假設" },
            { name: "P 計畫", type: "text", hint: "下一步處遇" },
            { name: "會談形式", type: "select", options: ["個別", "團體", "家長", "教師諮詢", "電話", "線上"],
              hint: "這一次是怎麼談的。" },
            { name: "會談次數", type: "text", hint: "這是第幾次會談？填數字就好，期末摘要照次數排序。" },
            { name: "風險評估", type: "select", options: ["無", "低", "中", "高"],
              hint: "有沒有立即的安全疑慮；期末會拉一條風險趨勢。" },
            { name: "下次時間", type: "date", hint: "下次約在什麼時候。" }
          ],
          tags: ["#初談", "#個別", "#團體", "#家長", "#教師諮詢", "#危機", "#結案"],
          custom: false
        }
      ],

      // 沒有自己指定 tags 的記錄類型，新增時就用這一組分類詞。
      categories: ["#課堂", "#主課程", "#學習態度", "#專注意志", "#人際", "#情緒", "#突破", "#個案", "#親師", "#生活"],
      help: {
        what: "一位學生一張卡，卡裡是你對他的觀察。上面那一排是「記錄類型」——質性評量、IEP、SOAP 各記各的，切過去只會看到那一種。整班層次的觀察記在「班級整體觀察」。",
        prepare: "一份學生名單（代號或座號＋姓名就夠了）。名單只放在你自己的電腦與你自己的資料庫，正文一律寫代號、不寫姓名。",
        ai: "把上課錄的音檔放進 inbox/，跟 AI 說「整理成學生記錄」；月底說「幫我看這個月誰還沒記」；學期末在明細頁按「產生期末素材」下載 .md，再把它整份貼給 AI。"
      }
    },

    courses: {
      enabled: true,
      categories: ["#進度", "#教學內容", "#學生反應", "#調整", "#亮點", "#卡點", "#規劃"],
      // 新增課程記錄時，正文預先帶這四段（用不到可以直接刪掉）
      skeleton: ["### 課程進度", "### 今天實際教了什麼", "### 學生整體反應", "### 下次要調整的"],
      help: {
        what: "一門課一張卡，卡裡是這門課每一次上完的記錄：講到哪、實際教了什麼、孩子怎麼反應、下次要調整什麼。提到個別學生請用代號。",
        prepare: "你想分開記的課程名稱就好。學季、週次、授課老師都是選填，留空不會顯示。",
        ai: "把課後隨手錄的音丟進 inbox/，跟 AI 說「整理成課程記錄」；期末說「把這一塊主課程的記錄整理成課程總結」。"
      }
    },

    business: {
      enabled: true,
      // 這位老師實際啟用的業務組。安裝時由他從下面的 businessLibrary 勾選，
      // 或用「我的業務不在清單裡」自訂（自訂的會帶 custom: true）。
      groups: [
        {
          id: "homeroom",
          label: "導師班務",
          fields: [
            { name: "學生/對象", type: "text" },
            { name: "事件", type: "text" },
            { name: "處理", type: "text" },
            { name: "後續", type: "text" }
          ],
          tags: ["#親師溝通", "#聯絡簿", "#家庭訪問", "#班親會", "#班級經營", "#出缺席", "#獎懲", "#班費", "#營養午餐"],
          custom: false
        },
        {
          id: "guidance",
          label: "輔導／個案追蹤",
          fields: [
            { name: "個案代號", type: "text" },
            { name: "來源", type: "select", options: ["導師轉介", "自行求助", "家長", "其他"] },
            { name: "主訴/議題", type: "text" },
            { name: "晤談摘要", type: "text" },
            { name: "評估", type: "text" },
            { name: "處遇/介入", type: "text" },
            { name: "追蹤與下次", type: "date" }
          ],
          tags: ["#初談", "#個別晤談", "#團體", "#家長晤談", "#轉介", "#通報", "#結案", "#追蹤"],
          custom: false
        },
        {
          id: "academic",
          label: "教務",
          fields: [
            { name: "事項", type: "text" },
            { name: "期限", type: "date" },
            { name: "狀態", type: "select", options: ["未開始", "進行中", "已完成", "已取消"] },
            { name: "備註", type: "text" }
          ],
          tags: ["#課程計畫", "#課表", "#成績/評量", "#教科書", "#補救教學", "#教學觀察", "#公開授課", "#教師研習"],
          custom: false
        }
      ],
      help: {
        what: "教學以外、但你每年都在做的事：班務、輔導個案、公文、會議、研習、報帳……一組業務一張卡，每組要記的欄位不一樣。",
        prepare: "先想清楚你手上有哪幾條線在跑。每一組還要決定「每次都要填的欄位」（例如期限、狀態、承辦人）與「常用分類詞」。",
        ai: "跟 AI 說「我還要加一組○○」，它會問清楚要記哪些欄位再寫進 config/tabs.json；說「這個月哪些業務逾期了」它會從記錄裡撈給你。"
      }
    }
  },

  // ── 業務組庫（給「＋ 新增業務組」勾選用）──────────────────────────
  // 正本＝config/business-groups.library.json（依台灣中小學處室分工整理）；
  // scripts/build_config.py 會把那一份的 groups 原樣搬進這個鍵。
  // [[待確認：業務組清單與欄位待 David 校對]]
  businessLibrary: [
    {
      id: "homeroom",
      label: "導師班務",
      desc: "班上每天在發生的事：聯絡簿、出缺席、獎懲、班費、親師溝通。",
      fields: [
        { name: "學生/對象", type: "text" },
        { name: "事件", type: "text" },
        { name: "處理", type: "text" },
        { name: "後續", type: "text" }
      ],
      tags: ["#親師溝通", "#聯絡簿", "#家庭訪問", "#班親會", "#班級經營", "#出缺席", "#獎懲", "#班費", "#營養午餐"]
    },
    {
      id: "guidance",
      label: "輔導／個案追蹤",
      desc: "個案的晤談與追蹤。個案一律用代號，可用「關聯」連回學生記錄。",
      fields: [
        { name: "個案代號", type: "text" },
        { name: "來源", type: "select", options: ["導師轉介", "自行求助", "家長", "其他"] },
        { name: "主訴/議題", type: "text" },
        { name: "晤談摘要", type: "text" },
        { name: "評估", type: "text" },
        { name: "處遇/介入", type: "text" },
        { name: "追蹤與下次", type: "date" }
      ],
      tags: ["#初談", "#個別晤談", "#團體", "#家長晤談", "#轉介", "#通報", "#結案", "#追蹤"]
    },
    {
      id: "special_ed",
      label: "特教／IEP",
      desc: "特教生的目標、課堂調整與會議決議。",
      fields: [
        { name: "個案代號", type: "text" },
        { name: "目標", type: "text" },
        { name: "觀察", type: "text" },
        { name: "調整/支持", type: "text" },
        { name: "會議決議", type: "text" }
      ],
      tags: ["#IEP", "#鑑定", "#巡迴", "#資源班", "#個案會議", "#轉銜"]
    },
    {
      id: "academic",
      label: "教務",
      desc: "課程計畫、課表、評量、公開授課這一類有期限的事項。",
      fields: [
        { name: "事項", type: "text" },
        { name: "期限", type: "date" },
        { name: "狀態", type: "select", options: ["未開始", "進行中", "已完成", "已取消"] },
        { name: "備註", type: "text" }
      ],
      tags: ["#課程計畫", "#課表", "#成績/評量", "#教科書", "#補救教學", "#教學觀察", "#公開授課", "#教師研習"]
    },
    {
      id: "student_affairs",
      label: "學務",
      desc: "生活教育、衛生保健、活動與安全事件。",
      fields: [],
      tags: ["#生活教育", "#衛生保健", "#體育活動", "#校外教學", "#防災演練", "#安全事件", "#品德/榮譽"]
    },
    {
      id: "general_affairs",
      label: "總務",
      desc: "報修、採購、請款、場地與財產。",
      fields: [],
      tags: ["#設備報修", "#採購", "#經費/請款", "#場地借用", "#財產盤點"]
    },
    {
      id: "paperwork",
      label: "公文／行政流程",
      desc: "承辦的公文與簽呈，追它辦到哪一步。",
      fields: [
        { name: "公文字號/來源", type: "text" },
        { name: "主旨", type: "text" },
        { name: "承辦", type: "text" },
        { name: "期限", type: "date" },
        { name: "辦理情形", type: "select", options: ["待辦", "辦理中", "已陳核", "已結案"] }
      ],
      tags: ["#公文", "#簽呈", "#調查表", "#計畫申請", "#成果報告"]
    },
    {
      id: "meetings",
      label: "會議紀錄",
      desc: "開過的會、誰在場、決議了什麼、誰要做什麼。",
      fields: [
        { name: "會議名稱", type: "text" },
        { name: "出席", type: "text" },
        { name: "決議", type: "text" },
        { name: "待辦", type: "text" }
      ],
      tags: ["#校務會議", "#教師晨會", "#年段會議", "#課發會", "#個案會議", "#IEP會議"]
    },
    {
      id: "pd",
      label: "研習／專業成長",
      desc: "研習、共備、觀議課、時數與證照。",
      fields: [],
      tags: ["#研習", "#共備", "#觀議課", "#讀書會", "#證照/時數"]
    },
    {
      id: "parent_comm",
      label: "家長／社區",
      desc: "家長會、志工、社區活動與捐贈。",
      fields: [],
      tags: ["#家長會", "#志工", "#社區活動", "#捐贈"]
    },
    {
      id: "personal",
      label: "個人待辦／雜項",
      desc: "不歸任何處室、但你不想忘記的事。",
      fields: [
        { name: "事項", type: "text" },
        { name: "期限", type: "date" },
        { name: "狀態", type: "select", options: ["未開始", "進行中", "已完成", "已取消"] }
      ],
      tags: ["#待辦", "#請假", "#報帳", "#備忘"]
    }
  ],

  // ── 學生記錄類型庫（給「＋ 選擇類型」勾選用）────────────────────────
  // 正本＝config/student-streams.library.json；scripts/build_config.py 會把那一份
  // 搬進這個鍵，並且**不搬**「我的類型不在清單裡」那一筆（開放選項，
  // 網頁上是最下面那個「我自己開一種」）。
  // scope: "class" ＝全班每一位學生都在；"case" ＝只有被列入的學生。
  // 每個 field 都有 hint＝表單裡那個欄位下方的一行灰字（v3 §3.6：記錄時每個欄位要有引導）。
  studentStreamLibrary: [
    {
      id: "qualitative",
      label: "質性評量觀察",
      desc: "方案①：不打分數的學校（實驗教育／私校）。每一則一個具體事件，先標面向與報告維度，期末一鍵分好組。",
      scope: "class",
      fields: [
        { name: "面向", type: "multiselect", options: ["頭·思考", "心·情感", "手·意志", "社群·人際"],
          hint: "這一則主要看見的是哪幾個面向？可以複選。" },
        { name: "報告維度", type: "select",
          options: ["行為與自我管理", "人際互動", "學習態度與能力", "內在特質與個人發展", "挑戰與方向"],
          hint: "期末評語照這五個維度分段；記的時候先標好，期末一鍵就分得出來。" },
        { name: "課程", type: "text", hint: "填課程名或科目" },
        { name: "證據來源", type: "select", options: ["工作本", "課堂觀察", "口說", "身體", "作品", "親師"],
          hint: "這一則是從哪裡看到的？寫得出來源，期末的話才站得住。" },
        { name: "指標", type: "text",
          hint: "「第N條 可獨立完成｜需輔助完成｜尚無法完成；情意類不打等級」" }
      ],
      tags: ["#課堂", "#主課程", "#學習態度", "#專注意志", "#人際", "#情緒", "#突破", "#親師", "#生活"]
    },
    {
      id: "homeroom",
      label: "導師班級學生紀錄",
      desc: "一般班務用的觀察簿：課堂上的具體事件、他當下的樣子、你看見的變化。全班每一位都在裡面。",
      scope: "class",
      fields: [],
      tags: ["#課堂", "#主課程", "#學習態度", "#專注意志", "#人際", "#情緒", "#突破", "#親師", "#生活"]
    },
    {
      id: "subject",
      label: "任課老師學生紀錄",
      desc: "科任老師記自己那一科看到的：這個孩子在我的課上是什麼樣子。",
      scope: "class",
      fields: [
        { name: "科目", type: "text", hint: "這一則是哪一科的課上看到的。" }
      ],
      tags: ["#課堂", "#學習態度", "#作業", "#專注", "#人際", "#亮點", "#卡點"]
    },
    {
      id: "iep",
      label: "IEP 個案追蹤",
      desc: "方案②：特教與早療。學生卡上先列這學期的目標，每一則對準一個目標，期末每個目標自動出一張表。",
      scope: "case",
      card: { goals: true },
      fields: [
        { name: "目標編號", type: "goal", hint: "從這位學生的目標清單挑一個；還沒有就先在上方「目標清單」加。" },
        { name: "達成情形", type: "select", options: ["未開始", "初步", "部分達成", "達成", "類化"],
          hint: "照這一次實際看到的填，不填期望值。" },
        { name: "證據", type: "select", options: ["觀察", "作品", "測驗", "家長回報"],
          hint: "這個判斷是從哪裡來的？" },
        { name: "支持策略", type: "text", hint: "這一次用了什麼調整或支持（提示、教具、環境、時間）。" },
        { name: "下一步", type: "text", hint: "只寫一個下一步，寫得出來才做得到。" }
      ],
      tags: ["#IEP", "#鑑定", "#資源班", "#巡迴", "#個案會議", "#轉銜", "#早療"]
    },
    {
      id: "soap",
      label: "諮商／個案 SOAP 紀錄",
      desc: "方案③：諮商、教練、社工。會談完照 S／O／A／P 四段拆，個案卡上放個案概念化。",
      scope: "case",
      aliases: ["counseling"],
      card: { conceptualization: true },
      fields: [
        { name: "S 主觀", type: "text", hint: "個案自己說的話與主觀感受" },
        { name: "O 客觀", type: "text", hint: "可觀察的行為與事實" },
        { name: "A 評估", type: "text", hint: "專業評估與假設" },
        { name: "P 計畫", type: "text", hint: "下一步處遇" },
        { name: "會談形式", type: "select", options: ["個別", "團體", "家長", "教師諮詢", "電話", "線上"],
          hint: "這一次是怎麼談的。" },
        { name: "會談次數", type: "text", hint: "這是第幾次會談？填數字就好，期末摘要照次數排序。" },
        { name: "風險評估", type: "select", options: ["無", "低", "中", "高"],
          hint: "有沒有立即的安全疑慮；期末會拉一條風險趨勢。" },
        { name: "下次時間", type: "date", hint: "下次約在什麼時候。" }
      ],
      tags: ["#初談", "#個別", "#團體", "#家長", "#教師諮詢", "#危機", "#結案"]
    },
    {
      id: "case",
      label: "個案追蹤（通用）",
      desc: "不走 SOAP 的通用個案簿：從哪裡來的、在意什麼、做了什麼、下次什麼時候看。",
      scope: "case",
      fields: [
        { name: "來源", type: "select", options: ["導師轉介", "自行求助", "家長", "輔導室", "其他"],
          hint: "這個個案是怎麼進來的。" },
        { name: "主訴／議題", type: "text", hint: "用他自己的說法寫，不要先翻譯成專業詞。" },
        { name: "處遇／介入", type: "text", hint: "這一次實際做了什麼。" },
        { name: "追蹤與下次", type: "date", hint: "下次要看的時間。" }
      ],
      tags: ["#初談", "#個別晤談", "#家長晤談", "#轉介", "#通報", "#結案"]
    }
  ],

  // ── 期末產出格式庫（v3 §3.6）──────────────────────────────────────
  // 正本＝config/report-formats.library.json。
  // 網頁明細頁的「產生期末素材 ▾」只列 for 含當前記錄類型的格式；
  // 產出的 .md ＝「確定性的分組素材」＋檔尾一段給 AI 的 prompt
  //（格式骨架 sections、書寫規則 rules、自我檢核 audit）。
  // 評語本文由老師自己的 AI 代理寫——這裡只給它素材與規則。
  reportFormats: [
    {
      id: "waldorf-homeroom",
      label: "質性評量素材包（導師版）",
      for: ["qualitative", "homeroom"],
      sections: [
        { title: "發展樣貌", hint: "這一年他整體長成什麼樣子。從一個具體畫面開始，不要從形容詞開始。", length: "約 150 字" },
        { title: "客觀描述：①行為與自我管理", hint: "看得見的事：他怎麼開始、怎麼收拾、怎麼面對規則。", length: "約 80 字" },
        { title: "客觀描述：②人際互動", hint: "他和同學、和老師之間發生過的具體事件。", length: "約 80 字" },
        { title: "客觀描述：③學習態度與能力", hint: "他怎麼進入一件事、卡住時做什麼、什麼時候是醒的。", length: "約 80 字" },
        { title: "客觀描述：④內在特質與個人發展", hint: "他自己說過的話、他在乎的東西、這一年的轉折。", length: "約 80 字" },
        { title: "客觀描述：⑤挑戰與方向", hint: "還沒有跨過去的地方，寫行為不寫本質。", length: "約 80 字" },
        { title: "整體感受", hint: "身為導師，你看見他的位置。可以有溫度，但仍要指得出證據。", length: "約 100 字" },
        { title: "導師建議", hint: "給家長一件他們回家做得到的事。只給一個。", length: "約 100 字" }
      ],
      rules: [
        "稱名不稱全名；人稱一律用「他」。",
        "先事實後判斷：每一段先給看得見的事，再給你的解讀。",
        "每一段只給一個下一步，不要開清單。",
        "禁「不是A而是B」這類對比句式。",
        "禁定型語言（「他就是很皮」「天生害羞」）——寫行為，不寫本質。",
        "不打分數、不排名；情意類永遠不給等級。",
        "只用素材包裡有的事實；素材裡沒有的不要補。"
      ],
      audit: [
        "每一段是不是都指得出一個具體事件或畫面？",
        "有沒有出現全名？（只能稱名）",
        "有沒有「不是…而是…」的句子？",
        "有沒有把行為說成本質？",
        "下一步是不是只有一個、而且家長做得到？",
        "字數有沒有落在每段指定的範圍？"
      ]
    },
    {
      id: "subject-4",
      label: "科任四段評語素材包",
      for: ["qualitative", "subject", "homeroom"],
      sections: [
        { title: "關係", hint: "他和這一科、和你之間的關係是什麼樣子。", length: "約 80 字" },
        { title: "參與", hint: "他在課堂上實際做了什麼（不是「很認真」，是他做了什麼）。", length: "約 100 字" },
        { title: "可見的學習證據", hint: "工作本、作品、口說、身體——指得出來的那一份。", length: "約 120 字" },
        { title: "下一步", hint: "下一段課程你打算怎麼接他。只給一個。", length: "約 80 字" }
      ],
      rules: [
        "全文 320–450 字。",
        "稱名不稱全名；人稱一律用「他」。",
        "先事實後判斷。",
        "禁「不是A而是B」這類對比句式。",
        "禁定型語言；寫行為不寫本質。",
        "只用素材包裡有的事實。"
      ],
      audit: [
        "全文字數在 320–450 之間嗎？",
        "「可見的學習證據」那一段有沒有指到具體的作品或場景？",
        "有沒有對比句式與定型語言？",
        "下一步是不是只有一個？"
      ]
    },
    {
      id: "iep-tracking",
      label: "IEP 追蹤報告素材包",
      for: ["iep"],
      sections: [
        { title: "每一個目標一段", hint: "照素材包裡每個目標的表寫：目標／評量方式與標準／日期序達成情形／證據／摘要。零紀錄的目標也要交代。", length: "每個目標約 120 字" },
        { title: "期末總評", hint: "這學期整體的達成樣貌與需要調整的支持。", length: "約 200 字" },
        { title: "會議紀錄（三段式）", hint: "述說前提／會議重點／日後發展目標。", length: "約 250 字" }
      ],
      rules: [
        "稱名不稱全名；人稱一律用「他」。",
        "每個目標的敘述先給日期序的事實，再給判斷。",
        "達成情形只能用素材包裡出現過的等級，不自行升級。",
        "零紀錄的目標要寫「本期無紀錄」，不要用推測補。",
        "每個目標只給一個下一步。",
        "禁「不是A而是B」這類對比句式；禁定型語言。"
      ],
      audit: [
        "每一個目標（含零紀錄的）都有一段嗎？",
        "達成情形有沒有超出素材包裡實際記到的等級？",
        "每個目標的下一步是不是只有一個？",
        "有沒有出現全名或定型語言？"
      ]
    },
    {
      id: "case-summary",
      label: "個案摘要／結案報告素材包",
      for: ["soap", "case"],
      sections: [
        { title: "個案概念化", hint: "照個案卡上的五欄：主訴／背景／評估假設／處遇目標／結案標準。", length: "約 200 字" },
        { title: "歷程摘要", hint: "依會談次數順序，每一次一句話帶過 S／O／A／P 的重點。", length: "每次約 60 字" },
        { title: "進展評估", hint: "對照處遇目標，現在到哪裡了；風險趨勢怎麼走。", length: "約 200 字" },
        { title: "處遇建議／結案評估", hint: "繼續談的建議，或結案的理由與後續銜接。", length: "約 200 字" }
      ],
      rules: [
        "稱名不稱全名；個案一律用代號，人稱用「他」。",
        "S 段只放個案自己說的話與主觀感受，不要混進你的評估。",
        "O 段只放可觀察的行為與事實。",
        "先事實後判斷；假設要標明是假設。",
        "風險等級只能照素材包裡記到的，不自行調高或調低。",
        "禁「不是A而是B」這類對比句式；禁定型語言。"
      ],
      audit: [
        "歷程摘要是不是照會談次數排的？",
        "有沒有把評估寫進 S 或 O？",
        "風險趨勢有沒有與素材包一致？",
        "結案評估有沒有對回個案卡上的結案標準？"
      ]
    },
    {
      id: "custom",
      label: "自訂格式（貼你們學校的格式）",
      for: ["qualitative", "homeroom", "subject", "iep", "soap", "case"],
      sections: [
        { title: "（把你們學校的格式標題貼在這裡）", hint: "一段一個標題，AI 會照你貼的順序與標題寫。", length: "依校方規定" }
      ],
      rules: [
        "先把校方的格式標題與字數規定貼在上面，再讓 AI 寫。",
        "稱名不稱全名；人稱一律用「他」。",
        "先事實後判斷；每一段只給一個下一步。",
        "禁「不是A而是B」這類對比句式；禁定型語言。",
        "只用素材包裡有的事實。"
      ],
      audit: [
        "校方要求的每一個標題都寫到了嗎？",
        "字數符合校方規定嗎？",
        "有沒有出現全名、對比句式或定型語言？"
      ]
    }
  ],

  // ── 方案庫（v3 §3.6）──────────────────────────────────────────────
  // 正本＝config/verticals.json。安裝精靈唸給老師聽、網頁「＋ 選擇類型」頂端
  // 也列這三張卡：**只建議，不預勾**——點一張只會在清單裡標「建議」徽章。
  verticals: [
    {
      id: "qualitative-assessment",
      label: "① 質性評量自動化（實驗教育／私校）",
      pain: "不打分數，期末卻要從一整年零碎的筆記回頭寫評語。",
      suggest: { streams: ["qualitative"], groups: ["homeroom", "academic"], format: "waldorf-homeroom" }
    },
    {
      id: "iep-tracking",
      label: "② IEP／早療追蹤",
      pain: "目標達成的細節很多、評鑑格式又繁瑣，寫報告等於把一學期重看一遍。",
      suggest: { streams: ["iep"], groups: ["special_ed", "meetings"], format: "iep-tracking" }
    },
    {
      id: "soap-casework",
      label: "③ 諮商／教練／社工 SOAP",
      pain: "每次會談後要寫 SOAP 或個案紀錄，手寫耗時又常漏細節。",
      suggest: { streams: ["soap"], groups: ["guidance"], format: "case-summary" }
    }
  ]
};
