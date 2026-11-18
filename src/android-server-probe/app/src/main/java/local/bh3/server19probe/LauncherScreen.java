package local.bh3.server19probe;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.Dialog;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.ColorFilter;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.text.TextUtils;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.style.ForegroundColorSpan;
import android.text.style.StyleSpan;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.*;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.Locale;

/** Native launcher presentation. All actions and progress come from IntegratedActivity. */
final class LauncherScreen {
    interface Actions {
        void selectResource();
        void selectSave();
        void exportSave();
        void editSave();
        void adjustServer();
        void changeDamage(boolean enabled);
        void start();
    }
    private final Activity activity;
    private final Actions actions;
    private final String notice;
    private final String[] themeNames={"黑灰","纯黑","深蓝灰","墨绿灰"};
    private final int[] backgrounds={0xff101113,0xff080809,0xff0b1016,0xff0b100e};
    private final int[] cards={0xff1b1d21,0xff171719,0xff1a2530,0xff1a2420};
    private final int[] accents={0xffb8c4d2,0xffceced4,0xffa8d0e8,0xffb4d6be};
    private final int white=0xffe9edf0,muted=0xff9ba4af,line=0xff393e44,green=0xffa7d3bd;
    private final String[] stepNames={"准备","校验","解压","存档","服务","启动"};
    private final ArrayList<String> events=new ArrayList<>();
    private final ArrayList<TextView> actionButtons=new ArrayList<>();
    private final File eventFile;
    private Bitmap heroArt,heroFrost;
    private int theme,stage;
    private long stageCompleted,stageTotal;
    private boolean enabled,canExport,running,failed,showLog,portraitExpanded,damage=true;
    private String latest="请确认资源包和存档后开始游戏。";
    private String resourceTitle="尚未选择",resourceState="未选择",resourceDetails="请选择配套视频 ZIP。";
    private String saveTitle="尚未选择",saveState="未选择",saveDetails="请选择服务端 JSON 存档。";
    private TextView monitorStatus,compactStatus,latestText,progressTitle,progressCount,logBody,logCount,startControl,exportControl;
    private ProgressBar progressBar;
    private Switch damageSwitch;
    private Steps steps;
    private ScrollView contentScroll;

    LauncherScreen(Activity activity,Actions actions,String notice){
        this.activity=activity;this.actions=actions;this.notice=notice;this.eventFile=new File(activity.getFilesDir(),"launcher-startup.log");
        if(eventFile.isFile())try(BufferedReader in=new BufferedReader(new InputStreamReader(new FileInputStream(eventFile),"UTF-8"))){String entry;while((entry=in.readLine())!=null){events.add(entry);if(events.size()>300)events.remove(0);}}catch(IOException error){android.util.Log.e("Server19Launcher","Unable to read launcher log",error);}
        theme=Math.max(0,Math.min(3,activity.getPreferences(Activity.MODE_PRIVATE).getInt("launcher_theme",0)));
        try(InputStream in=activity.getAssets().open("launcher-hero-bg.png")){
            BitmapFactory.Options options=new BitmapFactory.Options();options.inScaled=false;
            Bitmap original=BitmapFactory.decodeStream(in,null,options);
            if(original!=null){
                int x=Math.round(original.getWidth()*.034f),y=Math.round(original.getHeight()*.028f);
                heroArt=Bitmap.createBitmap(original,x,y,original.getWidth()-x*2,original.getHeight()-y*2);
                heroFrost=Bitmap.createScaledBitmap(heroArt,Math.max(1,heroArt.getWidth()/8),Math.max(1,heroArt.getHeight()/8),true);
            }
        }catch(IOException missing){android.util.Log.i("Server19Launcher","No optional launcher background");}
        record("启动页已加载");
    }
    private int d(float value){return (int)(value*activity.getResources().getDisplayMetrics().density+.5f);}
    private LinearLayout col(){LinearLayout v=new LinearLayout(activity);v.setOrientation(LinearLayout.VERTICAL);return v;}
    private LinearLayout row(){LinearLayout v=new LinearLayout(activity);v.setOrientation(LinearLayout.HORIZONTAL);v.setGravity(Gravity.CENTER_VERTICAL);return v;}
    private GradientDrawable shape(int color,int border,int radius){GradientDrawable v=new GradientDrawable();v.setColor(color);v.setCornerRadius(d(radius));if(border!=0)v.setStroke(d(1),border);return v;}
    private TextView text(String value,int size,int color,boolean bold){TextView v=new TextView(activity);v.setText(value);v.setTextSize(size);v.setTextColor(color);if(bold)v.setTypeface(Typeface.DEFAULT,Typeface.BOLD);return v;}
    private void add(LinearLayout parent,View child,int top){LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=d(top);parent.addView(child,lp);}
    private LinearLayout panel(int color){LinearLayout p=col();p.setPadding(d(16),d(14),d(16),d(14));p.setBackground(shape(color,line,14));return p;}
    private TextView section(String value){return text(value,11,muted,true);}
    private TextView button(String label,Runnable action){TextView v=text(label,9,0xffd0d4d9,true);v.setGravity(Gravity.CENTER);v.setPadding(d(8),d(8),d(8),d(8));v.setBackground(shape(0xff202327,line,7));v.setOnClickListener(w->action.run());return v;}
    private TextView action(String label,Runnable task){TextView v=text(label,12,accents[theme],true);v.setPadding(d(8),d(9),d(8),d(9));v.setOnClickListener(w->task.run());actionButtons.add(v);return v;}
    private void record(String message){
        String stamp=new SimpleDateFormat("yyyy-MM-dd HH:mm:ss",Locale.ROOT).format(new Date());
        String entry="["+stamp+"] "+message.replace('\r',' ').replace('\n',' ');events.add(entry);if(events.size()>300)events.remove(0);
        try(OutputStreamWriter out=new OutputStreamWriter(new FileOutputStream(eventFile,true),"UTF-8")){out.write(entry);out.write('\n');}catch(IOException error){android.util.Log.e("Server19Launcher","Unable to save launcher log",error);}
    }
    void status(String message){failed=false;latest=message;record(message);sync();}
    void hint(String message){latest=message;sync();}
    void failure(String message){failed=true;latest=message;record(message);sync();}
    void begin(){stage=0;stageCompleted=stageTotal=0;failed=false;portraitExpanded=true;record("开始准备游戏");render();}
    void stage(int completed,String message){stage=completed;stageCompleted=stageTotal=0;latest=message;record(message);sync();}
    void progress(int completedStages,String message,long completed,long total){stage=completedStages;stageCompleted=completed;stageTotal=total;latest=message;sync();}
    void controls(boolean enabled,boolean running,boolean canExport){this.enabled=enabled;this.running=running;this.canExport=canExport;sync();}
    void choices(boolean damage,String resourceTitle,String resourceState,String resourceDetails,String saveTitle,String saveState,String saveDetails){
        this.damage=damage;this.resourceTitle=resourceTitle;this.resourceState=resourceState;this.resourceDetails=resourceDetails;
        this.saveTitle=saveTitle;this.saveState=saveState;this.saveDetails=saveDetails;render();
    }
    private void sync(){
        for(TextView v:actionButtons){v.setEnabled(enabled);v.setAlpha(enabled?1f:.48f);}
        if(exportControl!=null){boolean can=enabled&&canExport;exportControl.setEnabled(can);exportControl.setAlpha(can?1f:.48f);}
        if(damageSwitch!=null)damageSwitch.setEnabled(enabled);
        if(startControl!=null){startControl.setEnabled(enabled);startControl.setAlpha(enabled?1f:.48f);startControl.setText(running?"正在准备游戏…":"开始游戏     →");}
        String heading=failed?"操作未完成":running?"正在准备游戏":"等待开始启动";
        if(monitorStatus!=null)monitorStatus.setText(failed?"操作未完成":running?"正在准备游戏":enabled?"等待开始":"处理中");
        if(compactStatus!=null){compactStatus.setText(latest);compactStatus.setMaxLines(2);compactStatus.setEllipsize(TextUtils.TruncateAt.END);}
        if(progressTitle!=null)progressTitle.setText(heading);
        if(progressCount!=null)progressCount.setText(stage+" / 6 步");
        if(progressBar!=null){int partial=stageTotal>0?(int)(1000*Math.max(0d,Math.min(1d,(double)stageCompleted/stageTotal))):0;progressBar.setProgress(Math.min(6000,stage*1000+partial));}
        if(steps!=null)steps.invalidate();
        if(latestText!=null)latestText.setText(latest);
        if(logBody!=null)logBody.setText(logText());
        if(logCount!=null)logCount.setText(events.size()+" EVENTS");
    }
    private String logText(){StringBuilder b=new StringBuilder();for(String event:events)b.append(event).append('\n');return b.toString();}
    private void openUrl(String url){try{activity.startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(url)));}catch(ActivityNotFoundException e){new AlertDialog.Builder(activity).setMessage("未找到可打开链接的应用。").setPositiveButton("知道了",null).show();}}

    private final class HeroArt extends Drawable {
        private final boolean landscape;private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG);
        HeroArt(boolean landscape){this.landscape=landscape;}
        @Override public void draw(Canvas canvas){
            android.graphics.Rect b=getBounds();float width=b.width(),height=b.height();if(width<=0||height<=0)return;
            int outer=canvas.save();canvas.translate(b.left,b.top);RectF rect=new RectF(0,0,width,height);Path round=new Path();round.addRoundRect(rect,d(14),d(14),Path.Direction.CW);canvas.clipPath(round);
            paint.setColor(0xff20242a);paint.setShader(null);canvas.drawRect(rect,paint);
            if(heroArt!=null){
                float scale=Math.max(width/heroArt.getWidth(),height/heroArt.getHeight())*1.01f;
                float iw=heroArt.getWidth()*scale,ih=heroArt.getHeight()*scale;
                float left=(width-iw)*(landscape?.57f:.60f),top=(height-ih)*(landscape?.23f:.34f);
                RectF image=new RectF(left,top,left+iw,top+ih);paint.setColor(Color.WHITE);canvas.drawBitmap(heroArt,null,image,paint);
                if(heroFrost!=null){int glass=canvas.save();Path p=new Path();p.moveTo(0,0);p.lineTo(width*(landscape?.48f:.55f),0);p.lineTo(width*(landscape?.36f:.43f),height);p.lineTo(0,height);p.close();canvas.clipPath(p);
                    paint.setAlpha(135);canvas.drawBitmap(heroFrost,null,image,paint);paint.setAlpha(255);
                    paint.setShader(new LinearGradient(0,0,width*.58f,0,new int[]{0x800a1019,0x500c121a,0x18101820},null,Shader.TileMode.CLAMP));canvas.drawRect(rect,paint);paint.setShader(null);
                    paint.setColor(0x12ffffff);canvas.drawRect(rect,paint);canvas.restoreToCount(glass);}
                paint.setColor(0x79070a10);canvas.drawRect(rect,paint);
                paint.setShader(new LinearGradient(0,0,0,height,0x2004080e,0x6604080e,Shader.TileMode.CLAMP));canvas.drawRect(rect,paint);paint.setShader(null);
                paint.setShader(new LinearGradient(0,0,width*.70f,0,0x64080b10,0x00080b10,Shader.TileMode.CLAMP));canvas.drawRect(rect,paint);paint.setShader(null);
                paint.setColor(0x5206090e);canvas.drawRect(0,height*.76f,width,height,paint);
            }
            canvas.restoreToCount(outer);paint.setShader(null);paint.setColor(0xff535962);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(d(1));
            canvas.drawRoundRect(new RectF(b.left+d(.5f),b.top+d(.5f),b.right-d(.5f),b.bottom-d(.5f)),d(14),d(14),paint);paint.setStyle(Paint.Style.FILL);
        }
        @Override public void setAlpha(int alpha){paint.setAlpha(alpha);invalidateSelf();}
        @Override public void setColorFilter(ColorFilter filter){paint.setColorFilter(filter);invalidateSelf();}
        @Override public int getOpacity(){return PixelFormat.TRANSLUCENT;}
    }
    private void shadow(View view){if(view instanceof TextView)((TextView)view).setShadowLayer(d(2),0,d(1),0xcc000000);else if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++)shadow(group.getChildAt(i));}}
    private LinearLayout hero(boolean compact){
        LinearLayout h=panel(0xff24272b);h.setBackground(new HeroArt(compact));h.setPadding(d(compact?14:18),d(compact?9:14),d(compact?14:18),d(compact?8:14));
        LinearLayout top=row();top.addView(text("LEGACY PROJECT / 2017",compact?8:11,muted,true),new LinearLayout.LayoutParams(0,-2,1));top.addView(text("●  LOCAL BUILD",compact?8:10,green,true));h.addView(top);
        add(h,text(compact?"崩壞3rd · 2017":"崩壞3rd  ·  2017",compact?23:26,white,true),compact?4:12);
        String subtitle="LOC-RENASCI 项目   /   V0.2.0";TextView sub=text(subtitle,compact?10:12,0xffc0c5ca,compact);
        SpannableString highlighted=new SpannableString(subtitle);int version=subtitle.indexOf("V0.2.0");highlighted.setSpan(new ForegroundColorSpan(0xffb9dcf1),version,subtitle.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);highlighted.setSpan(new StyleSpan(Typeface.BOLD),version,subtitle.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);sub.setText(highlighted);add(h,sub,compact?1:3);
        if(compact){View divider=new View(activity);divider.setBackgroundColor(line);LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,d(1));p.topMargin=d(6);h.addView(divider,p);}
        LinearLayout bottom=row();bottom.addView(text("由 GitHub/ClearwSea 适配",compact?9:10,muted,false),new LinearLayout.LayoutParams(0,-2,1));
        TextView update=text("检查更新 ↗",compact?9:12,white,true);update.setPadding(d(6),d(compact?4:9),0,d(compact?4:9));update.setOnClickListener(v->openUrl("https://github.com/ClearwSea/BH2017-LOCRENASCI/releases/latest"));bottom.addView(update);add(h,bottom,compact?0:12);shadow(h);return h;
    }
    private LinearLayout notice(boolean compact){
        LinearLayout p=panel(0xff24221f);p.setPadding(d(compact?12:16),d(compact?8:12),d(compact?12:16),d(compact?8:12));
        LinearLayout h=row();h.addView(text("△   重要公告",compact?12:14,0xffe3c69e,true),new LinearLayout.LayoutParams(0,-2,1));h.addView(text("NOTICE",compact?8:9,0xffaf9779,true));p.addView(h);
        TextView body=text("项目仅供数字遗产保存与学习交流，版权归米哈游所有\n------------------\n禁止倒卖；如果你是花钱付费获取，说明你被骗了，请申请退款并举报。",compact?10:12,0xffc7b9a7,false);body.setLineSpacing(d(compact?2:3),1);add(p,body,compact?4:8);
        TextView details=text("查看完整公告  →",compact?9:10,0xffe3c69e,true);details.setGravity(Gravity.RIGHT);details.setPadding(0,d(compact?3:7),0,0);details.setOnClickListener(v->noticeDialog());add(p,details,compact?2:4);return p;
    }
    private void noticeDialog(){
        Dialog pop=new Dialog(activity);LinearLayout box=col();box.setPadding(d(22),d(20),d(20),d(20));box.setBackground(shape(0xff1b1e22,0xff34383d,16));
        LinearLayout header=row();header.addView(text("重要公告",19,white,true),new LinearLayout.LayoutParams(0,-2,1));header.addView(button("×",pop::dismiss),new LinearLayout.LayoutParams(d(38),d(38)));box.addView(header);
        TextView body=text("",13,0xffb6bcc5,false);LauncherNotice.setText(body,notice);body.setTextColor(0xffb6bcc5);body.setLinkTextColor(accents[theme]);body.setLineSpacing(d(6),1);
        ScrollView scrolling=new ScrollView(activity);scrolling.addView(body);LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,0,1);lp.topMargin=d(20);box.addView(scrolling,lp);
        LinearLayout footer=row();footer.setGravity(Gravity.RIGHT);footer.addView(button("我知道了",pop::dismiss));add(box,footer,22);pop.setContentView(box);pop.show();if(pop.getWindow()!=null){pop.getWindow().setBackgroundDrawableResource(android.R.color.transparent);pop.getWindow().setLayout(Math.min(d(460),activity.getResources().getDisplayMetrics().widthPixels-d(32)),Math.min(d(400),activity.getResources().getDisplayMetrics().heightPixels-d(48)));}
    }
    private void themeDialog(){
        Dialog pop=new Dialog(activity);LinearLayout box=col();box.setPadding(d(18),d(16),d(18),d(16));box.setBackground(shape(cards[theme],line,14));
        LinearLayout header=row();header.addView(text("界面主题",17,white,true),new LinearLayout.LayoutParams(0,-2,1));header.addView(button("×",pop::dismiss));box.addView(header);add(box,text("当前："+themeNames[theme],11,muted,false),8);
        for(int i=0;i<themeNames.length;i++){final int selected=i;LinearLayout option=row();option.setPadding(d(12),d(9),d(12),d(9));option.setBackground(shape(backgrounds[i],i==theme?accents[theme]:line,8));option.addView(text(themeNames[i],13,white,true),new LinearLayout.LayoutParams(0,-2,1));option.addView(text(i==theme?"✓ 已选择":"选择",10,i==theme?green:muted,true));option.setOnClickListener(v->{theme=selected;activity.getPreferences(Activity.MODE_PRIVATE).edit().putInt("launcher_theme",theme).apply();pop.dismiss();render();});add(box,option,7);}
        ScrollView scroll=new ScrollView(activity);scroll.addView(box);pop.setContentView(scroll);pop.show();if(pop.getWindow()!=null){pop.getWindow().setBackgroundDrawableResource(android.R.color.transparent);pop.getWindow().setLayout(Math.min(d(360),activity.getResources().getDisplayMetrics().widthPixels-d(32)),Math.min(d(350),activity.getResources().getDisplayMetrics().heightPixels-d(40)));}
    }
    private void detailDialog(boolean resource){
        new AlertDialog.Builder(activity).setTitle(resource?"资源包路径":"存档路径").setMessage(resource?resourceDetails:saveDetails).setPositiveButton("关闭",null).show();
    }
    private LinearLayout resource(boolean isResource){
        LinearLayout p=panel(cards[theme]);LinearLayout h=row();h.addView(text((isResource?"▧   游戏资源包":"▣   游戏存档"),14,white,true),new LinearLayout.LayoutParams(0,-2,1));String state=isResource?resourceState:saveState;int stateColor=state.equals("已导入")?green:state.startsWith("待")?0xffe3c69e:muted;h.addView(text("●  "+state,10,stateColor,true));TextView details=button("⋯",()->detailDialog(isResource));details.setTextSize(19);details.setPadding(d(8),d(2),d(8),d(2));details.setContentDescription(isResource?"资源包详情":"存档详情");LinearLayout.LayoutParams detailParams=new LinearLayout.LayoutParams(-2,-2);detailParams.leftMargin=d(8);h.addView(details,detailParams);p.addView(h);
        TextView title=text(isResource?resourceTitle:saveTitle,12,white,true);title.setMaxLines(2);title.setEllipsize(TextUtils.TruncateAt.END);add(p,title,10);
        add(p,text(isResource?"配套视频资源 ZIP":"服务端 JSON 存档",10,muted,false),2);
        LinearLayout buttons=row();buttons.addView(action("选择 / 更换  →",isResource?actions::selectResource:actions::selectSave));if(!isResource){exportControl=action("导出当前存档",actions::exportSave);buttons.addView(exportControl);}add(p,buttons,6);return p;
    }
    private LinearLayout toolCard(){
        LinearLayout p=col();p.addView(section("02 / UTILITIES"));add(p,text("功能工具",15,white,true),4);LinearLayout cards=row();cards.setGravity(Gravity.TOP);
        LinearLayout editor=toolTile("存档编辑","查看和修改存档","✎");editor.setAlpha(1f);editor.setOnClickListener(v->actions.editSave());
        cards.addView(editor,new LinearLayout.LayoutParams(0,-2,1));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-2,1);lp.leftMargin=d(10);
        LinearLayout server=toolTile("服务端调整","本地活动与深渊设置","☷");server.setAlpha(1f);server.setOnClickListener(v->actions.adjustServer());cards.addView(server,lp);add(p,cards,9);return p;
    }
    private LinearLayout toolTile(String name,String description,String icon){LinearLayout p=panel(cards[theme]);p.setPadding(d(12),d(10),d(12),d(10));p.setAlpha(.64f);p.addView(text(icon,12,accents[theme],true));add(p,text(name,12,white,true),7);add(p,text(description,9,muted,false),3);return p;}
    private LinearLayout settings(){LinearLayout p=panel(cards[theme]);LinearLayout r=row();LinearLayout labels=col();labels.addView(text("辅助伤害 20×",12,white,true));add(labels,text("需要完全重启游戏实现",9,muted,false),3);r.addView(labels,new LinearLayout.LayoutParams(0,-2,1));damageSwitch=new Switch(activity);damageSwitch.setChecked(damage);damageSwitch.setOnCheckedChangeListener((v,checked)->{damage=checked;actions.changeDamage(checked);});r.addView(damageSwitch);p.addView(r);return p;}
    private final class Steps extends View {
        Steps(){super(activity);}
        @Override protected void onDraw(Canvas c){super.onDraw(c);float width=getWidth(),gap=width/6f,cy=d(12),radius=d(8);Paint p=new Paint(3);p.setStrokeWidth(d(1));p.setColor(0xff373b40);c.drawLine(gap/2,cy,width-gap/2,cy,p);
            for(int i=0;i<6;i++){float x=gap*(i+.5f);boolean done=i<stage,active=running&&i==stage;p.setStyle(Paint.Style.FILL);p.setColor(done?0xff203029:active?0xff42484e:0xff101215);c.drawCircle(x,cy,radius,p);p.setStyle(Paint.Style.STROKE);p.setColor(done?0xff91b3a2:active?0xffc5cdd6:0xff3a3e43);c.drawCircle(x,cy,radius,p);p.setStyle(Paint.Style.FILL);p.setTypeface(Typeface.create(Typeface.DEFAULT,Typeface.BOLD));p.setTextSize(d(9));p.setTextAlign(Paint.Align.CENTER);p.setColor(done?0xffa8c7b7:active?0xffeef0f3:0xff858d97);c.drawText(done?"✓":Integer.toString(i+1),x,cy+d(3),p);p.setTypeface(Typeface.DEFAULT);p.setTextSize(d(8));p.setColor(done?0xffa4c4b1:0xff9ba4af);c.drawText(stepNames[i],x,cy+d(22),p);}
        }
    }
    private TextView startButton(boolean landscape){TextView v=text("开始游戏     →",landscape?14:15,0xff111518,true);v.setGravity(Gravity.CENTER);v.setBackground(shape(accents[theme],0,8));v.setOnClickListener(w->actions.start());startControl=v;return v;}
    private LinearLayout dock(boolean landscape){
        LinearLayout p=col();p.setPadding(landscape?d(14):0,d(9),landscape?d(13):0,d(7));p.setBackgroundColor(cards[theme]);
        LinearLayout top=row();top.addView(text("●  LOCAL RUNTIME",9,green,true),new LinearLayout.LayoutParams(0,-2,1));if(landscape)top.addView(button("⚙ 主题",this::themeDialog));else top.addView(button("收起 ⌄",()->{portraitExpanded=false;render();}));p.addView(top);add(p,text("启动控制台",16,white,true),4);
        LinearLayout mon=col();mon.setPadding(d(landscape?8:12),d(7),d(landscape?8:12),d(7));mon.setBackground(shape(0xff1b1f23,line,10));LinearLayout mh=row();mh.addView(text("◷  LAUNCH MONITOR / 启动状态",landscape?8:9,muted,true),new LinearLayout.LayoutParams(0,-2,1));mon.addView(mh);
        monitorStatus=text("系统就绪",landscape?11:12,white,true);add(mon,monitorStatus,3);
        ScrollView scroll=new ScrollView(activity);scroll.setVerticalScrollBarEnabled(true);LinearLayout details=col();details.setPadding(0,d(5),0,0);scroll.addView(details);
        LinearLayout title=row();progressTitle=text("等待开始启动",9,white,true);title.addView(progressTitle,new LinearLayout.LayoutParams(0,-2,1));progressCount=text("0 / 6 步",9,muted,false);title.addView(progressCount);details.addView(title);
        progressBar=new ProgressBar(activity,null,android.R.attr.progressBarStyleHorizontal);progressBar.setMax(6000);progressBar.setProgressTintList(android.content.res.ColorStateList.valueOf(0xffc2c9d1));progressBar.setProgressBackgroundTintList(android.content.res.ColorStateList.valueOf(0xff303439));LinearLayout.LayoutParams bar=new LinearLayout.LayoutParams(-1,d(4));bar.topMargin=d(7);details.addView(progressBar,bar);
        steps=new Steps();LinearLayout.LayoutParams sp=new LinearLayout.LayoutParams(-1,d(42));sp.topMargin=d(7);details.addView(steps,sp);
        LinearLayout last=row();last.setPadding(d(8),d(6),d(8),d(6));last.setBackground(shape(0xff101316,0xff303439,7));last.addView(text("LATEST",8,0xffb6c0cc,true));latestText=text(latest,8,0xffc3c9d0,false);LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-2,1);lp.leftMargin=d(6);last.addView(latestText,lp);add(details,last,3);
        LinearLayout buttons=row();buttons.addView(button(showLog?"收起详细日志 ↑":"查看详细日志 ↓",()->{showLog=!showLog;render();}));LinearLayout.LayoutParams cb=new LinearLayout.LayoutParams(-2,-2);cb.leftMargin=d(5);buttons.addView(button("复制日志",()->{ClipboardManager clipboard=(ClipboardManager)activity.getSystemService(Activity.CLIPBOARD_SERVICE);clipboard.setPrimaryClip(ClipData.newPlainText("启动日志",logText()));Toast.makeText(activity,"已复制启动日志",Toast.LENGTH_SHORT).show();}),cb);add(details,buttons,7);
        if(showLog){LinearLayout log=col();log.setPadding(d(8),d(7),d(8),d(7));log.setBackground(shape(0xff101316,0xff303439,7));LinearLayout lh=row();lh.addView(text("EXECUTION LOG",8,muted,true),new LinearLayout.LayoutParams(0,-2,1));logCount=text("",8,muted,true);lh.addView(logCount);log.addView(lh);logBody=text(logText(),8,0xffbcc4cb,false);logBody.setTypeface(Typeface.MONOSPACE);logBody.setLineSpacing(d(2),1);add(log,logBody,6);add(details,log,7);}
        mon.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));LinearLayout.LayoutParams ml=new LinearLayout.LayoutParams(-1,0,1);ml.topMargin=d(7);ml.bottomMargin=d(7);p.addView(mon,ml);p.addView(startButton(landscape),new LinearLayout.LayoutParams(-1,d(42)));return p;
    }
    void render(){
        int oldScroll=contentScroll==null?0:contentScroll.getScrollY();boolean landscape=activity.getResources().getConfiguration().orientation==Configuration.ORIENTATION_LANDSCAPE;
        monitorStatus=compactStatus=latestText=progressTitle=progressCount=logBody=logCount=startControl=exportControl=null;progressBar=null;steps=null;damageSwitch=null;actionButtons.clear();
        activity.getWindow().setStatusBarColor(backgrounds[theme]);activity.getWindow().setNavigationBarColor(backgrounds[theme]);LinearLayout root=col();root.setBackgroundColor(backgrounds[theme]);activity.setContentView(root);
        if(!landscape){LinearLayout toolbar=row();toolbar.setPadding(d(14),d(3),d(14),d(3));toolbar.addView(text("BH2017 / 启动器",9,muted,true),new LinearLayout.LayoutParams(0,-2,1));toolbar.addView(button("⚙ 主题",this::themeDialog));root.addView(toolbar);}
        LinearLayout body=row();body.setGravity(Gravity.TOP);root.addView(body,new LinearLayout.LayoutParams(-1,0,1));contentScroll=new ScrollView(activity);contentScroll.setFillViewport(true);contentScroll.setClipToPadding(false);body.addView(contentScroll,new LinearLayout.LayoutParams(0,-1,1));LinearLayout content=col();content.setPadding(d(18),d(14),d(18),d(18));contentScroll.addView(content);
        if(landscape){content.setPadding(d(16),d(9),d(16),d(20));if(activity.getResources().getConfiguration().screenWidthDp>=850){LinearLayout intro=row();intro.setGravity(Gravity.TOP);intro.addView(hero(true),new LinearLayout.LayoutParams(0,-2,1));LinearLayout.LayoutParams np=new LinearLayout.LayoutParams(0,-2,1);np.leftMargin=d(10);intro.addView(notice(true),np);content.addView(intro);}else{content.addView(hero(true));add(content,notice(true),10);}
            add(content,section("01 / STARTUP FILES   ·   启动准备"),13);if(activity.getResources().getConfiguration().screenWidthDp>=800){LinearLayout cards=row();cards.setGravity(Gravity.TOP);cards.addView(resource(true),new LinearLayout.LayoutParams(0,-2,1));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-2,1);lp.leftMargin=d(10);cards.addView(resource(false),lp);add(content,cards,8);}else{add(content,resource(true),8);add(content,resource(false),8);}add(content,toolCard(),14);add(content,section("03 / PREFERENCES    ·    游戏设置"),14);add(content,settings(),7);body.addView(dock(true),new LinearLayout.LayoutParams(d(250),-1));
        }else{content.addView(hero(false));add(content,notice(false),10);add(content,section("01 / STARTUP FILES     ·     启动准备"),16);add(content,resource(true),8);add(content,resource(false),8);add(content,toolCard(),14);add(content,section("03 / PREFERENCES    ·    游戏设置"),14);add(content,settings(),7);
            LinearLayout foot=col();foot.setPadding(d(12),d(5),d(12),d(8));foot.setBackgroundColor(cards[theme]);root.addView(foot);if(portraitExpanded)foot.addView(dock(false),new LinearLayout.LayoutParams(-1,d(340)));else{LinearLayout status=row();status.setPadding(d(12),d(7),d(12),d(7));status.setBackground(shape(cards[theme],line,10));LinearLayout summary=col();summary.addView(text("◷  LAUNCH MONITOR / 启动状态",9,muted,true));compactStatus=text(latest,12,white,true);add(summary,compactStatus,3);status.addView(summary,new LinearLayout.LayoutParams(0,-2,1));status.addView(button("展开 ⌃",()->{portraitExpanded=true;render();}));status.setOnClickListener(v->{portraitExpanded=true;render();});foot.addView(status);TextView start=startButton(false);start.setPadding(0,d(12),0,d(12));add(foot,start,8);}}
        ScrollView restored=contentScroll;restored.post(()->restored.scrollTo(0,oldScroll));sync();
    }
}
