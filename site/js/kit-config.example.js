/* ══════════════════════════════════════════════════════════════════════
   kit-config.example.js — 網站設定的「範本」
   ──────────────────────────────────────────────────────────────────────
   實際使用的 site/js/kit-config.js **不要手寫**：
   由 scripts/build_config.py 讀 config/kit.json ＋ config/tabs.json 產生
   （產生檔已被 .gitignore 擋住）。本檔只是形狀範例與預設文案來源。

   本檔用傳統的 script 標籤載入（不是 module），
   載完之後全域只多一個 window.KIT。
   ══════════════════════════════════════════════════════════════════════ */

window.KIT = {

  // true＝示範模式：完全不連 Firebase，資料只存在這個瀏覽器（localStorage）。
  // 網址加 ?demo=1 也會進示範模式。build_preview.py 產生的單檔預覽固定為 true。
  demo: false,

  // 只有這個 Google 帳號會被當成擁有者（要與 firestore.rules 裡的一致）
  ownerEmail: "you@example.com",

  // 學生代號前綴（名冊代號長這樣：S-01、S-02…）
  idPrefix: "S-",

  // ── 三個分頁（形狀與 config/tabs.json 完全一致）────────────────────
  tabs: {

    students: {
      enabled: true,
      categories: ["#課堂", "#主課程", "#學習態度", "#專注意志", "#人際", "#情緒", "#突破", "#個案", "#親師", "#生活"],
      help: {
        what: "一位學生一張卡，卡裡是你對他的觀察：課堂上發生的具體事件、他當下的樣子、你看見的變化。整班層次的觀察記在「班級整體觀察」。",
        prepare: "一份學生名單（代號或座號＋姓名就夠了）。名單只放在你自己的電腦與你自己的資料庫，正文一律寫代號、不寫姓名。",
        ai: "把上課錄的音檔放進 inbox/，跟 AI 說「整理成學生記錄」；月底說「幫我看這個月誰還沒記」；學期末說「把 S-03 這學期的記錄整理成家長會要講的重點」。"
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
  // 正本＝docs/business-groups-draft.yaml（依台灣中小學處室分工整理）。
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
  ]
};
