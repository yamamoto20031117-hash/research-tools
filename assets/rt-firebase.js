/* =====================================================================
   research-tools 共通 Firebase 設定（唯一の正）

   以前は index.html / xrd-plotter / cfms-plotter / dmm-monitor /
   dmm-monitor-2 の 5 箇所に同じリテラルを直書きしていたが、
   index.html 以外の 4 つは messagingSenderId と appId がプレースホルダ
   （"359837086498" / "...:web:your_app_id"）のまま残っていた。
   ここには index.html にあった正しい値だけを置いている。

   設定を変えるときはこのファイルだけを直すこと。
   ===================================================================== */
window.RT_FIREBASE_CONFIG = {
  apiKey: "AIzaSyClK3vIE_SQ7SGdXWbmWzZ51MdeBappDKY",
  authDomain: "research-tools-board.firebaseapp.com",
  databaseURL: "https://research-tools-board-default-rtdb.firebaseio.com",
  projectId: "research-tools-board",
  storageBucket: "research-tools-board.firebasestorage.app",
  messagingSenderId: "919441103197",
  appId: "1:919441103197:web:2bb09e95d4b3034648f0b4",
  measurementId: "G-7JCBM41RH4"
};
