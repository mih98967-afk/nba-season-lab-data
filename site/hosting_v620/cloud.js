/* Firebase Auth + Firestore. Every participant owns a separate document.
 * No paid Firebase Cloud Functions or App Hosting are used.
 */
const config=window.FIREBASE_CONFIG||{};
const enabled=['apiKey','authDomain','projectId','appId'].every(k=>typeof config[k]==='string'&&config[k].length>5);
let client=null,firestore=null,user=null,ref=null,dirtyTimer=null,pending=null,ready=false,loading=false,lastUid=null;
const setStatus=(state,label,email=null)=>{window.NBA_CLOUD_STATUS={state,label,user:email};window.NBA?.view?.();};
setStatus(enabled?'loading':'unconfigured',enabled?'Подключение облака':'Только локальное сохранение');
if(enabled){
 try{
  const [appSdk,authSdk,dbSdk]=await Promise.all([
   import('https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js'),
   import('https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js'),
   import('https://www.gstatic.com/firebasejs/11.10.0/firebase-firestore.js')
  ]);
  const {initializeApp}=appSdk;
  const {getAuth,onAuthStateChanged,signInWithEmailAndPassword,createUserWithEmailAndPassword,signOut}=authSdk;
  const {getFirestore,doc,getDoc,setDoc}=dbSdk;
  client=getAuth(initializeApp(config));firestore=getFirestore(client.app);
  onAuthStateChanged(client,async(u)=>{
   ready=false;user=u;ref=null;
   if(!u){if(lastUid)window.NBA?.guestReset?.();lastUid=null;setStatus('guest','Без входа · только этот браузер');return;}lastUid=u.uid;
   setStatus('loading','Загружаем личный состав…',u.email);
   ref=doc(firestore,'users',u.uid,'seasons','2026-27');
   try{
    loading=true;
    const snap=await getDoc(ref);
    if(user!==u)return;
    if(snap.exists()&&snap.data()?.state?.v===5){window.NBA.applyState(snap.data().state);}
    else {
     const state=window.NBA.getState();
     // Do not auto-publish browser's guest state without asking.
     if(state.roster?.length===10 && confirm('В облаке нет сохранённой команды. Скопировать ваш локальный состав в личный аккаунт?')){
      await setDoc(ref,{state,updatedAt:new Date().toISOString(),schema:5});
     }else {window.NBA.guestReset();}
    }
    ready=true;setStatus('online','Облачная синхронизация',u.email);
   }catch(e){setStatus('error','Не удалось открыть облачный состав: '+(e.code||e.message),u.email);}
   finally{loading=false;}
  });
  window.nbaCloudSave=(state)=>{
   if(!ready||!user||!ref||loading)return;
   pending=state;clearTimeout(dirtyTimer);
   dirtyTimer=setTimeout(async()=>{
    const toSave=pending;pending=null;
    if(!toSave||!user||!ready||!ref)return;
    try{
     setStatus('saving','Сохраняем изменения…',user.email);
     await setDoc(ref,{state:toSave,updatedAt:new Date().toISOString(),schema:5});
     if(pending===null)setStatus('online','Сохранено в облаке',user.email);
    }catch(e){setStatus('error','Ошибка сохранения: '+(e.code||e.message),user.email);}
   },800);
  };
  document.addEventListener('click',async(e)=>{
   const b=e.target.closest('[data-cloud]');if(!b)return;
   const type=b.dataset.cloud;
   if(type==='logout'){
    // Prevent queued state from one account crossing into another login.
    clearTimeout(dirtyTimer);pending=null;ready=false;await signOut(client);return;
   }
   const email=document.querySelector('#cloud-email')?.value?.trim();
   const password=document.querySelector('#cloud-password')?.value;
   if(!email||!password||password.length<8){alert('Нужны email и пароль минимум из 8 символов');return;}
   b.disabled=true;
   try{
    if(type==='login')await signInWithEmailAndPassword(client,email,password);
    if(type==='signup')await createUserWithEmailAndPassword(client,email,password);
   }catch(e){setStatus('error','Не удалось войти: '+(e.code||e.message));}
   finally{b.disabled=false;}
  });
 }catch(e){setStatus('error','Firebase SDK недоступен. Локальный режим работает.');}
}
