import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import pinia from './store'

// 导入Vant组件库
import {
  Button,
  NavBar,
  Tabbar,
  TabbarItem,
  Tab,
  Tabs,
  List,
  PullRefresh,
  Cell,
  CellGroup,
  Grid,
  GridItem,
  Empty,
  Form,
  Field,
  Image,
  Toast,
  Icon,
  Popup,
  Dialog,
  RadioGroup,
  Radio,
  Loading,
  Tag,
  Switch,
  Checkbox,
  CheckboxGroup,
  Stepper,
  Slider,
  Uploader,
  Search,
  Sticky,
  Swipe,
  SwipeItem,
  ActionSheet,
  Picker,
  DatePicker,
  TimePicker,
  Cascader,
  NumberKeyboard,
  PasswordInput,
  Sidebar,
  SidebarItem,
  TreeSelect,
  IndexBar,
  IndexAnchor,
  Badge,
  Circle,
  Progress,
  Skeleton,
  DropdownMenu,
  DropdownItem,
  NoticeBar,
  Divider,
  Rate,
  Collapse,
  CollapseItem,
  Step,
  Steps,
  ImagePreview,
  Lazyload,
  Overlay
} from 'vant'

// 导入Vant样式
import 'vant/lib/index.css'

// 导入全局样式
import './style.css'

// 引入国际化
import { setupI18n } from './i18n'

const app = createApp(App)

// 设置i18n
const i18n = setupI18n()
app.use(i18n)

// 注册Vant组件
app.use(Button)
app.use(NavBar)
app.use(Tabbar)
app.use(TabbarItem)
app.use(Tab)
app.use(Tabs)
app.use(List)
app.use(PullRefresh)
app.use(Cell)
app.use(CellGroup)
app.use(Grid)
app.use(GridItem)
app.use(Empty)
app.use(Form)
app.use(Field)
app.use(Image)
app.use(Toast)
app.use(Icon)
app.use(Popup)
app.use(Dialog)
app.use(RadioGroup)
app.use(Radio)
app.use(Loading)
app.use(Tag)
app.use(Switch)
app.use(Checkbox)
app.use(CheckboxGroup)
app.use(Stepper)
app.use(Slider)
app.use(Uploader)
app.use(Search)
app.use(Sticky)
app.use(Swipe)
app.use(SwipeItem)
app.use(ActionSheet)
app.use(Picker)
app.use(DatePicker)
app.use(TimePicker)
app.use(Cascader)
app.use(NumberKeyboard)
app.use(PasswordInput)
app.use(Sidebar)
app.use(SidebarItem)
app.use(TreeSelect)
app.use(IndexBar)
app.use(IndexAnchor)
app.use(Badge)
app.use(Circle)
app.use(Progress)
app.use(Skeleton)
app.use(DropdownMenu)
app.use(DropdownItem)
app.use(NoticeBar)
app.use(Divider)
app.use(Rate)
app.use(Collapse)
app.use(CollapseItem)
app.use(Step)
app.use(Steps)
app.use(ImagePreview)
app.use(Lazyload)
app.use(Overlay)

// 使用路由和状态管理
app.use(router)
app.use(pinia)

app.mount('#app')

// 初始化主题
import { useThemeStore } from './store/theme'
const themeStore = useThemeStore()
themeStore.initTheme()
