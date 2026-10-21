// ! function (e, t, n, a, s, i, o) {
//     e[s] || (e.GlobalSnowplowNamespace = e.GlobalSnowplowNamespace || [], e.GlobalSnowplowNamespace.push(s), e[s] = function () {
//         (e[s].q = e[s].q || []).push(arguments)
//     }, e[s].q = e[s].q || [], i = t.createElement(n), o = t.getElementsByTagName(n)[0], i.async = 1, i.src = a, o.parentNode.insertBefore(i, o))
// }(window, document, "script", res_cninfo_url+"/js/plugin/sp.js", "snowplow"), window.snowplow("newTracker", "web_tracker", "tj.cninfo.com.cn", {
//     encodeBase64: !1,
//     appId: "cninfo",
//     platform: "web",
//     buffersize: 0,
//     discoverRootDomain: !1,
//     pageUnloadTimer: 0,
//     useCookies: true
// });
//巨潮用户信息
var JC_USER = {
    isLogin: false,
    userInfo: {},
    setUserInfo: function (info) {
        this.userInfo = info;
    },
    getUser: function () {
        return this.userInfo;
    },
    getInfo: function (key) {
        return this.userInfo[key] ? this.userInfo[key] : '';
    },
    setLoginStatus: function (status) {
        this.isLogin = status;
    },
    getLoginStatus: function () {
        return this.isLogin;
    }
}
//弹窗登录回调地址
var LOGIN_CB_URL = '/';
//弹窗登录回调类型
var LOGIN_CB_TYPE = '';

function myBrowser() {
    var userAgent = navigator.userAgent; //取得浏览器的userAgent字符串
    var isOpera = userAgent.indexOf("Opera") > -1;
    if (isOpera) {
        return "Opera"
    } //判断是否Opera浏览器
    if (userAgent.indexOf("Firefox") > -1) {
        return "FF";
    } //判断是否Firefox浏览器
    if (userAgent.indexOf("Chrome") > -1) {
        return "Chrome";
    }
    if (userAgent.indexOf("Safari") > -1) {
        return "Safari";
    } //判断是否Safari浏览器
    if (userAgent.indexOf("compatible") > -1 && userAgent.indexOf("MSIE") > -1 && !isOpera) {
        return "IE";
    } //判断是否IE浏览器
    if (userAgent.indexOf("rv") > -1) {
        return "IE";
    }
}

//防抖函数
function debounce(fn, delay) {
    var timer = null;
    return function () {
        if (timer) {
            clearTimeout(timer);
        }
        timer = setTimeout(fn.bind(this), delay);
    }
}

//三位数字计算
function thousands(num) {
    return (num || 0).toString().replace(/(\d)(?=(?:\d{3})+$)/g, '$1,');
}

//全角转半角
function ToCDb(strs) {
    var str = strs;
    var result = "";
    if (str == null || str == "") {
        return result;
    }
    for (var i = 0; i < str.length; i++) {
        if (str.charCodeAt(i) == 12288) {
            result += String.fromCharCode(str.charCodeAt(i) - 12256);
            continue;
        }
        if (str.charCodeAt(i) > 65280 && str.charCodeAt(i) < 65375)
            result += String.fromCharCode(str.charCodeAt(i) - 65248);
        else
            result += String.fromCharCode(str.charCodeAt(i));
    }
    return result;
}

//半角转全角
function ToDBC(strs) {
    var str = strs
    var tmp = "";
    if (str == null || str == "") {
        return '';
    }
    for (var i = 0; i < str.length; i++) {
        if (str.charCodeAt(i) == 32) {
            tmp = tmp + String.fromCharCode(12288);
        } else if (str.charCodeAt(i) < 127) {
            tmp = tmp + String.fromCharCode(str.charCodeAt(i) + 65248);
        } else {
            tmp += tmp
        }
    }
    return tmp;
}

//获取URL参数值
function getUrlParam() {
    var args = {};
    var query = location.search.substring(1); //获取查询串
    var pairs = query.split("&"); //在逗号处断开
    for (var i = 0; i < pairs.length; i++) {
        var pos = pairs[i].indexOf('='); //查找name=value
        if (pos == -1) { //如果没有找到就跳过
            continue;
        }
        var argname = pairs[i].substring(0, pos); //提取name
        var value = pairs[i].substring(pos + 1); //提取value
        args[argname] = decodeURI(value); //存为属性
    }
    return args; //返回对象
}

//个股页地址
function stockHref(data) {
    return path + '/disclosure/stock?stockCode=' + (data.stockCode ? data.stockCode : data.secCode) + '&orgId=' + data.orgId;
}

function stockHref2(data) {
    return path + '/disclosure/stock?stockCode=' + data.code + '&plate=' + data.plateCode;
}

//公告页地址
function PdfHref(data) {
    return path + '/disclosure/detail?stockCode=' + (data.stockCode ? data.stockCode : data
        .secCode) + '&announcementId=' + data.announcementId + '&announcementTime=' + fomatDate(data.announcementTime, 'yyyy-MM-dd');
}

function PdfHref2(data) {
    return path + '/disclosure/detail?stockCode=' + data.code + '&announcementId=' + data.id + '&announcementTime=' + fomatDate(data.announcementTime, 'yyyy-MM-dd');
}


//在线浏览地址
function viewOnline(data) {
    var linkUrl = '';
    if (data.adjunctType == 'PPT' || data.adjunctType == 'PPTX' ||
        data.adjunctType == "XLS" || data.adjunctType == "XLSX" ||
        data.adjunctType == "CSV" || data.adjunctType == "PNG" ||
        data.adjunctType == "DOC" || data.adjunctType == "DOCX") {
        linkUrl = officeUrl + encodeURIComponent(v3_cninfo + '/' + data.adjunctUrl);

    } else {
        linkUrl = path + '/disclosure/detail?stockCode=' + (data.secCode ? data.secCode : '') +
            '&announcementId=' + (data.announcementId ? data.announcementId : '') +
            '&orgId=' + (data.orgId ? data.orgId : '') +
            '&announcementTime=' + fomatDate(data.announcementTime, 'yyyy-MM-dd')
    }
    return linkUrl
}

//首页banner预加载图片
function preLoadImg(name, errorSrc) {
    var imgWrap = [];
    var avatorImg = $(name);
    avatorImg.each(function (index) {
        var _this = this;
        imgWrap[index] = new Image();
        imgWrap[index].src = $(_this).attr('data-src');
        imgWrap[index].onload = function () {
            $(_this).attr('src', imgWrap[index].src);
            // $(_this).show();
        }
        imgWrap[index].onerror = function () {
            $(_this).attr('src', errorSrc);
            // $(_this).show();
        }
    })
}

function getHistoryWd() {
    var str = localStorage.getItem('historyWd');
    return str ? JSON.parse(str) : [];
}

function setHistoryWd(word) {
    var list = getHistoryWd();
    if (list) {
        var hasWord = list.filter(function (item) {
            return item == word;
        }).length > 0 ? true : false;

        if (!hasWord) {
            list.unshift(word)
            localStorage.setItem('historyWd', JSON.stringify(list.slice(0, 5)));
        }
    } else {
        localStorage.setItem('historyWd', JSON.stringify(list.push(word)));
    }
}

function getSearchHistory() {
    var str = localStorage.getItem('searchHistory');
    return str ? JSON.parse(str) : [];
}

function setSearchHistory(word){
    var list = getSearchHistory();
    if (list) {
        var hasWord = list.filter(function (item) {
            return item == word;
        }).length > 0 ? true : false;

        if (!hasWord) {
            list.unshift(word)
            localStorage.setItem('searchHistory', JSON.stringify(list.slice(0, 6)));
        }
    } else {
        localStorage.setItem('searchHistory', JSON.stringify(list.push(word)));
    }
}

function delHistoryWd(word) {
    var list = getHistoryWd();
    if (list) {
        var newList = list.filter(function (item) {
            return item != word;
        });
        localStorage.setItem('historyWd', JSON.stringify(newList));
    }
}


function tdClickPosition(eventId, label, params) {
    var kv = null;
    if (null != params && '' != params) {
        kv = {
            "_td_click_position": params
        };
    }
    // eventTracker(eventId, label, kv);
}

// //用户行为分析，行为事件调用
// function eventTracker(eventId, label, params) {
//     if (!window.TDAPP) {
//         return;
//     }
//
//     try {
//         window.TDAPP.onEvent(eventId, label, params);
//     } catch (e) {
//         // TODO 捕获到了异常应该如何处理
//     }
// }
//
// //用户行为分析，自定义页面跳转统计调用
// function eventTrackerOfPage(pageName, pageTitle) {
//     if (!window.TDAPP) {
//         return;
//     }
//
//     try {
//         if (pageName && pageTitle) {
//             window.TDAPP.onCustomPage(pageName, pageTitle);
//         }
//     } catch (e) {
//         // TODO 捕获到了异常应该如何处理
//         alert(e);
//
//     }
// }

function gotoUC(){
 $.ajax({
        url: cninfo_user_url + '/api/user/info',
        method: 'get',
        withCredentials: true,
        xhrFields: {
                withCredentials: true
        },
        async: false,
        params: {
            str: Math.random()
        },
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        },
        success: function(data) {
                JC_USER.setLoginStatus(data.code == 200 ? true : false);
                if (data.code == 200) {
                    window.open(cninfo_user_url,"_self");
                }else  if (data.code == 402) {
                    LOGIN_CB_URL = window.location.href;
                    var loginurl=cninfo_user_url_https + '/logout?locale=zh&service='+encodeURIComponent(LOGIN_CB_URL);
                    window.open(loginurl,"_self");
                }else{
                    var loginurl=cninfo_user_url_https + '/login?locale=zh&service='+cninfo_user_url+encodeURIComponent('/api/callback?client_name=CasClient');
                    window.open(loginurl,"_self");
                }
        }
   })
}
//获取用户信息

function getCommonUserInfo(callBack) {
    $.ajax({
        url: cninfo_user_url + '/api/user/info',
        method: 'get',
        withCredentials: true,
        xhrFields: {
                withCredentials: true
        },
        async: false,
        params: {
            str: Math.random()
        },
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        },
        success: function(data) {
                    JC_USER.setLoginStatus(data.code == 200 ? true : false);
                    if (data.code == 200) {
                        JC_USER.setUserInfo(data.data);
                        try{
                            $('.handle-wrap .nolog').hide()
                            $('.handle-wrap .logged').show()
                            if (JC_USER.getInfo('nickname')) {
                                $('.logged .logged-name').html(JC_USER.getInfo('nickname'));
                            } else {
                                $('.logged .logged-name').html('巨潮用户');
                            }
                            if (JC_USER.getInfo('headImage')) {
                                $('.logged .avator-img')[0].src = JC_USER.getInfo('headImage');
                            }
                        }catch(e){
                            //donothing
                        }

                        // getNotice({url: , params:,}).then(noticeTip.display =show ,noticeTip.data = res.data)
                        axios({
                            url: cninfo_user_url+'/api/station/newsStat',
                            method: 'get'
                        }).then(function (res) {
                            noticeTip.display = true;
                            noticeTip.newsNew = res.data;
                        }).catch(function (err) {

                        })
                    } else  if (data.code == 402) {
                        // $('.handle-wrap .nolog').show()
                        // $('.handle-wrap .logged').hide()
                        // LOGIN_CB_TYPE = '';
                        //清楚旧的token
                        LOGIN_CB_URL = window.location.href;
                        var loginurl=cninfo_user_url_https + '/logout?locale=zh&service='+encodeURIComponent(LOGIN_CB_URL);
                        window.open(loginurl,"_self");

                    }
                    if (callBack) {
                        callBack()
                    }
        },
         error: function(xhr, status, error) {
                LOGIN_CB_TYPE = '';
            }
    })
}

var topSearchElm = {
    focusStauts: false,
    setFocusStatus: function (status) {
        this.focusStauts = status
    },
    getFocusStatus: function () {
        return this.focusStauts
    }
}
var noticeTip = '';
var Feed_Back = '';
$(function () {
    //顶部搜索框
    var TopSearch = Vue.extend({
        template: '   <el-autocomplete' +
            '                            ref="topSearch"' +
            '                            size="small"' +
            '                            class="search-input"' +
            '                            popper-class="top-sh top-auto"' +
            '                            maxlength="30"' +
            '                            placeholder="代码/简称/拼音/关键字"' +
            '                            v-model="keyWord"' +
            '                            :trigger-on-focus="true "' +
            '                            :fetch-suggestions="querySearch"' +
            '                            :debounce="200"' +
            '                            :popper-append-to-body="false"' +
            '                            :hide-loading="true"' +
            '                            @keyup.enter.native="enterQuery"' +
            '                            @focus="inputFocus"' +
            '                            @blur="inputBlur"' +
            '                            @select="handleSelect"' +
            '                            @input="topSearchInput"' +
            '>' +

            '                        <el-button type="text" class="chaxun-btn" @click.stop="clickSearch()" slot="suffix"><i class="el-input__icon iconfont iconchaxun"></i></el-button>' +
            '                        <p>热门搜索</p>' +
            '                        <template slot-scope="item">' +
            // '                            <div >' +
            '                                <el-row v-if="keyWordTemPalte() && stockList.length == 0">' +
            '                                    <el-col>' +
            '                                        <span  v-if="item.item.type ==\'title\'"><i class="iconfont" :class="item.item.icon"></i> {{item.item.ct}}</span>' +
            '                                        <span class="hisword ell" :title="item.item.word" v-else-if="item.item.type == \'word\'">' +
            '                                    {{item.item.word}}' +
            '                                    <el-button class="hisword-d" type="text" size="mini" @click.stop="delBtn(item.item)"><i class="iconfont iconshanchu"></i></el-button>' +
            '                                </span>' +
            '                                        <span v-else class="ell" :title="item.item.word">' +
            '                                    <svg class="icon  c-icon" aria-hidden="true">' +
            '                                        <use :xlink:href="item.item.icon"></use>' +
            '                                    </svg>' +
            '                                    {{item.item.word&&item.item.word.length>8?item.item.word.slice(0,8)+(\'...\'):item.item.word}}' +
            '                                </span>' +
            '                                    </el-col>' +
            '                                </el-row>' +
            '                                <el-row v-if="stockList.length > 0" :gutter="10">' +
            '                                    <el-col :span="7">' +
            '                                        <span class="code">{{item.item.code}}</span>' +
            '                                    </el-col>' +
            '                                    <el-col :span="5">' +
            '                                        <span class="type ell" :title="item.item.category">{{item.item.category}}</span>' +
            '                                    </el-col>' +
            '                                    <el-col :span="12">' +
            '                                        <span class="name" :title="item.item.zwjc" v-if="item.item.zwjc&&item.item.zwjc.length>8">{{item.item.zwjc.slice(0,8)}}...</span>' +
            '                                        <span class="name ell" :title="item.item.zwjc" v-else>{{item.item.zwjc}}</span>' +
            '                                    </el-col>' +
            '                                </el-row>' +
            // '                            </div>' +
            '                        </template>' +
            '                    </el-autocomplete>',
        data: function () {
            return {
                keyWord: "", //关键字
                keyWordOne: '',
                maxNum: 10,
                historyMap: {
                    type: 'title',
                    ct: '历史搜索',
                    icon: 'iconlishi'
                },
                hotMap: {
                    type: 'title',
                    ct: '热门搜索',
                    icon: 'iconremen'
                },
                delItem: {},
                firstList: [],
                historyList: [], //历史查询
                hotwordList: [], //下拉热词
                stockList: [], //下拉个股
                // seniorList: [], //下拉高管
                selectItem: {
                    code: '',
                    orgId: ''
                }, //选中代码
            }

        },
        methods: {
            topSearchInput: function(value){
                Bus.$emit('TopSearchInput_Full_Event',value)
            },
            inputFocus: function () {
                topSearchElm.setFocusStatus(true);
            },
            inputBlur: function () {
                topSearchElm.setFocusStatus(false);
            },
            keyWordTemPalte: function() {
                var _this = this
                var keyFlag = _this.keyWord === undefined ? !_this.keyWord:!_this.keyWord.trim()
                return keyFlag
            },
            querySearch: function (queryString, cb) {
                var qs = queryString === undefined ? queryString:queryString.trim()
                var _this = this;
                this.keyWordOne = this.keyWord
                if (!qs) {
                    this.stockList = [];
                    // this.seniorList = [];
                    this.getHotSearch(cb);
                    // cb([]);
                } else {
                    this.getCodeList(cb);
                    // this.getSeniorList(cb);
                }
            },
            delBtn: function (item) {
                this.delItem = item;
                delHistoryWd(item.word);
                this.$refs.topSearch.handleFocus();
            },
            //输入框 回车事件
            enterQuery: function (event) {
                // eventTracker('进入全局搜索结果页面', '顶部输入框回车');
                var _this = this;
                var keyWord = this.keyWord;
                var re = /select|update|delete|exec|count|……|，|\*|——|【|】|[|]|{|}|、|“|”|《|》|。|‘|’|'|"|=|~|!|\+|\(|\)|\\|\/|\?|\$|;|>|<|:|：|\^|&|@|#|%/i;

                if (re.test(keyWord.trim())) {
                    alert("存在非法字符，请重新输入");
                    this.keyWord = '';
                    return;
                }

                if(this.keyWord.trim()){
                    this.goSearch(this.keyWord.trim());
                }

                // if (this.stockList.length > 0) {
                //     var item = this.stockList[0];
                //     if (item.zwjc) {
                //         setHistoryWd(item.zwjc);
                //     } else if (item.humanname) {
                //         setHistoryWd(item.humanname);
                //     }
                //     window.open(path + '/disclosure/stock?stockCode=' + item.code + '&orgId=' + item.orgId);
                // } else if (this.keyWord.trim()) {
                //     this.goSearch(this.keyWord.trim());
                // }
            },
            clickSearch: function () {
                var _this = this;
                var titleKeyword = this.keyWord;
                var re = /select|update|delete|exec|count|……|，|\*|——|【|】|[|]|{|}|、|“|”|《|》|。|‘|’|'|"|=|~|!|\+|\(|\)|\\|\/|\?|\$|;|>|<|:|：|\^|&|@|#|%/i;

                if (re.test(titleKeyword.trim())) {
                    alert("存在非法字符，请重新输入");
                    this.keyWord = '';
                    return;
                }
                if (this.keyWord.trim()) {
                    // eventTracker('进入公司页面', '顶部搜索按钮点击');
                    setHistoryWd(this.keyWord.trim());
                    localStorage.removeItem("searchHistory")
                    localStorage.removeItem('dateVd')
                    localStorage.removeItem('pickerMd')
                    localStorage.removeItem('checkedCities')
                    setSearchHistory(this.keyWord.trim())
                    window.location.href = path + '/fulltextSearch?notautosubmit=&keyWord=' + this.keyWord.trim();
                }
            },
            goSearch: function (word) {
                setHistoryWd(word);
                localStorage.removeItem("searchHistory");
                localStorage.removeItem('dateVd')
                localStorage.removeItem('pickerMd')
                localStorage.removeItem('checkedCities')
                setSearchHistory(word);
                window.location.href = path + '/fulltextSearch?notautosubmit=&keyWord=' + word;
            },
            handleSelect: function (item) {
                // eventTracker('进入公司页面', '顶部键盘精灵点击');
                this.selectItem = item;
                if (item.zwjc) {
                    setHistoryWd(item.zwjc);
                } else if (item.humanname) {
                    setHistoryWd(item.humanname);
                }

                if (item.word) {
                    this.goSearch(item.word);
                } else if (item.humanname) {
                    this.goSearch(item.humanname);
                } else if (item.code) {
                    window.location.href = path + '/disclosure/stock?stockCode=' + item.code + '&orgId=' + item.orgId + '&sjstsBond=' + item.sjstsBond;
                }
                this.keyWord = this.keyWordOne
                if(item.type == 'title'){
                    Bus.$emit('TopSearchInput_Full_Event',this.keyWordOne)
                }
            },
            delHistory: function (item) {
                delHistoryWd(item.word);
            },
            // getSeniorList: function (cb,arr) {
            //     var _this = this;
            //     axios({
            //         url: path + "/executive/recommend",
            //         method: 'post',
            //         params: {
            //             name: ToCDb(this.keyWord.trim()).toLowerCase(),
            //         }
            //     }).then(function (res) {
            //         if (res.docs && res.docs.length > 0) {
            //             var sArr = arr
            //             _this.seniorList = res.docs;
            //             sArr = sArr.concat([{ type: "title", ct: "高管", icon: "icon-remen" }],res.docs)
            //             cb(sArr);
            //         } else {
            //             _this.seniorList = [];
            //             cb(arr)
            //             // if (_this.stockList.length == 0) {
            //             //     cb([]);
            //             // }
            //         }
            //     }).catch(function (err) {
            //         cb([]);
            //     })
            // },
            // getSeniorList: function (cb) {
            //     var _this = this;
            //     axios({
            //         url: path + "/executive/recommend",
            //         method: 'post',
            //         params: {
            //             name: ToCDb(this.keyWord).toLowerCase(),
            //         }
            //     }).then(function (res) {
            //         if (res.docs && res.docs.length > 0) {
            //             _this.seniorList = res.docs;
            //             cb(_this.seniorList);
            //         } else {
            //             _this.seniorList = [];
            //             if (_this.stockList.length == 0) {
            //                 cb([]);
            //             }
            //         }
            //     }).catch(function (err) {
            //         cb([]);
            //     })
            // },
            getCodeList: function (cb) {
                var _this = this;
                // path
                axios({
                    url: path + "/information/topSearch/query",
                    method: 'post',
                    params: {
                        keyWord: ToCDb(this.keyWord.trim()).toLowerCase() || keyWord,
                        maxNum: this.maxNum
                    }
                }).then(function (res) {
                    var sArr = []
                    if (res && res.length > 0) {
                        _this.stockList = res;
                        sArr = sArr.concat([{ type: "title", ct: "证券", icon: "icon-remen" }],res)
                        cb(sArr);
                        // _this.getSeniorList(cb,sArr)
                    } else {
                        _this.stockList = [];
                        if (_this.seniorList.length == 0) {
                            cb([]);
                        }
                        // _this.getSeniorList(cb,[]);
                    }
                }).catch(function (err) {
                    cb([]);
                })
            },
            // getCodeList: function (cb) {
            //     var _this = this;
            //     axios({
            //         url: path + "/information/topSearch/query",
            //         method: 'post',
            //         params: {
            //             keyWord: ToCDb(this.keyWord).toLowerCase(),
            //             maxNum: this.maxNum
            //         }
            //     }).then(function (res) {
            //         if (res && res.length > 0) {
            //             _this.stockList = res;
            //             cb(_this.stockList);
            //         } else {
            //             _this.stockList = [];
            //             if (_this.seniorList.length == 0) {
            //                 cb([]);
            //             }
            //         }
            //     }).catch(function (err) {
            //         cb([]);
            //     })
            // },
            getHotSearch: function (cb) {
                var _this = this;
                axios({
                    url: path + "/fulltextSearch/hotwordspage",
                    method: 'post',
                }).then(function (res) {
                    if (res) {
                        var resData = res.map(function (item, index) {
                            item.icon = '#iconre' + (index - 0 + 1);
                            return item
                        })
                        var fArr = [];
                        var historyWds = getHistoryWd().map(function (item) {
                            return {
                                type: 'word',
                                word: item
                            }
                        });
                        if (historyWds.length > 0) {
                            fArr = fArr.concat([_this.historyMap], historyWds);
                            // fArr = fArr.concat([_this.historyMap], historyWds, [_this.hotMap], resData);
                        } else {
                            // fArr = fArr.concat([_this.hotMap], resData);
                        }
                        cb(fArr);
                    } else {
                        _this.hotwordList = [];
                        cb([]);
                    }
                })
            }
        },
        created: function () {},
        mounted: function () {
            var self = this
            if(PAGE_TYPE=='fullSearch'){
                this.keyWord = keyWord
                Bus.$on('FullSearch_Bus_Event',function(item){
                    self.keyWord = item
                })
            }
        },
        beforeDestroy: function(){
            Bus.$off('FullSearch_Bus_Event')
        }
    });
    var ts1 = new TopSearch().$mount('.top-search-1');
    var ts2 = new TopSearch().$mount('.top-search-2');
    //免责声明
    var statement = new Vue({
        el: '#statement',
        data: function () {
            return {
                stateVisible: false
            }
        }
    })
    //反馈
    Feed_Back = new Vue({
        el: '#feedback',
        data: function () {
            return {
                dialogVisible: false,
                msg: ''
            }
        },
        methods: {
            openDialog: function () {
                // eventTracker('首页_侧边栏反馈');
                window.open('http://www.szse.cn/index/feedback/index.html?service=cninfo&module=2&auth=09ulul0fblOholSeUcLEQvGVxwOtSVMq', '_blank');
                // var _this = this;
                // if (!JC_USER.getLoginStatus()) {
                //     LOGIN_CB_TYPE = 'feedback_open';
                //     $('#loginWrapper').show();
                //     $('#login_iframe').attr('src', cninfo_user_url_https + '/login?locale=zh&service='+cninfo_user_url_https + encodeURIComponent('/api/callback?client_name=CasClient&url=' + window.location.origin + '/new/transition'));
                // } else {
                //     _this.msg = '';
                //     _this.dialogVisible = true;
                // }
            },
            confirmDialog: function () {
                var _this = this;
                if (_this.msg == '' || !_this.msg) return;
                axios({
                    url: cninfo_user_url + "/api/user/feedback/addFeedback",
                    method: 'post',
                    params: {
                        'content': this.msg
                    }
                }).then(function (res) {
                    _this.dialogVisible = false;
                    if (res.code == 200 && res.data) {
                        _this.$message({
                            message: '反馈成功',
                            type: 'success'
                        })
                    }

                }).catch(function (err) {
                    if (err.response.data) {
                        _this.$message({
                            message: err.response.data.msg,
                            type: 'error'
                        })
                    }

                })
            }
        }
    })
    // 站内消息
    noticeTip = new Vue({
        el: '#noticeTipId',
        data: function () {
            return {
                display: false,
                visible: false,
                newsNew: null
            }
        },
        methods: {
            readNewsStatus: function () {
                var self = this;
                axios({
                    url: cninfo_user_url+'/api/station/readNews?type=all',
                    method: 'post',
                }).then(function (res) {
                    if (res.data) {
                        self.newsNew.read = true;
                    }
                }).catch(function (err) {

                })
            },
            toRouter: function (rout, modul) {
                if (modul) {
                    window.location.href = cninfo_user_url + rout + '?dataMoudle=' + modul;
                } else {
                    window.location.href = cninfo_user_url + rout;
                }
            }
        }
    })

    //二级页面顶部图
    if (!(PAGE_TYPE == 'index' || PAGE_TYPE == 'lucencyhd')) {
        getSecondPageImg();

        function getSecondPageImg() {
            axios({
                url: path + '/index/getPictureByColumnMark?columnMark=nxtGgPic',
                method: 'post'
            }).then(function (res) {
                // console.log(res);
                if (res && res.nxtGgPic && (res.nxtGgPic.length > 0) && res.nxtGgPic[0].path) {
                    $('.second-hd-img').css('background-image', 'url(' + v3_cninfo + res.nxtGgPic[0].path + ')')
                }
            })
        }
    }

    //查询用户信息
    getCommonUserInfo();


    function switchHeader(hd, top, ht) {
        if (topSearchElm.getFocusStatus()) return;
        if (top > ht) {
            hd.find('.scroll-hd').addClass('is-shown');
            hd.find('.base-hd').addClass('is-hidden')
        } else {
            hd.find('.scroll-hd').removeClass('is-shown')
            hd.find('.base-hd').removeClass('is-hidden')
        }

    }

    var scorllHdStatus = false; //防止重复滚动执行
    var MOUSE_ENTER_HD = false;
    if (PAGE_TYPE == 'index') {} else {
        $('header').mouseenter(function () {
            MOUSE_ENTER_HD = true;
            scorllHeader($(this), 1, true);
        })
        $('header').mouseleave(function () {
            MOUSE_ENTER_HD = false;
            scorllHeader($(this), $(document).scrollTop(), false);
        })
    }

    function scorllHeader(hd, top, isHover) {

        if ((!scorllHdStatus && top > 0) || isHover) {
            scorllHdStatus = true;
            hd.removeClass('transparent-hd');
            hd.addClass('jc-shadow-2');

        } else if (top == 0) {
            scorllHdStatus = false;
            hd.addClass('transparent-hd');
            hd.removeClass('jc-shadow-2');
        }
    }

    //监听滚动条
    $(window).scroll(function () {
        var hdEl = $('header');
        var top = $(document).scrollTop();

        var scrollTop = $(this).scrollTop();
        var scrollHeight = $(document).height();
        var windowHeight = $(this).height();

        if (PAGE_TYPE == 'index') {
            // switchHeader(hdEl, top, 440);
        } else {
            if (PAGE_TYPE == 'secondScrollhd') {
                // switchHeader(hdEl, top, 220);
            }
            scorllHeader(hdEl, top, MOUSE_ENTER_HD);
        }
        if (top < 600) {
            $('.backtop').removeClass('active')
        } else {
            $('.backtop').addClass('active')
        }

        if(PAGE_TYPE == 'fullSearch'){
            if(top < 280){
                $('.search-wrap-full').removeClass('wrap-full-block')
                // $('.el-autocomplete-suggestion.top-sh').remove()
            }else{
                $('.search-wrap-full').addClass('wrap-full-block')
                // $('.el-autocomplete-suggestion.top-sh').removeClass('wrap-full-sug')
            }
        }

        if (scrollTop + windowHeight == scrollHeight) {
            $('.right-bar').addClass('closeBottom')
        } else {
            $('.right-bar').removeClass('closeBottom')
        }
        var leftNavDom = $('.person-stock-news .left-nav')
        if (leftNavDom) {
            if (top > 200) {
                leftNavDom.addClass('left-nav-min')
            } else {
                leftNavDom.removeClass('left-nav-min')
            }
        }

    })
    $(".reloadPage").click(function () {
        setTimeout(function () {
            location.reload()
        }, 1000)
    })
    //返回顶部
    $('.backtop').click(function () {
        $('html,body').animate({
            scrollTop: 0
        }, 350)
    })
    //图片预加载
    preLoadiImg();

    function preLoadiImg() {
        var imgWrap = [];
        var mainBannerImg = $('.mainBannerImg');
        mainBannerImg.each(function (index) {
            var _this = this;
            imgWrap[index] = new Image();
            imgWrap[index].src = $(_this).attr('data-src');
            imgWrap[index].onload = function () {
                $(_this).attr('src', imgWrap[index].src);
            }
        })
    }

    //侧边栏APP
    // https://owssso.szse.cn/sso/login?locale=zh&service=https://uc.cninfo.com.cn/api/callback?client_name=CasClient
    $('.my-subs').click(function () {
        // if (JC_USER.getLoginStatus()) {
        //     window.open(cninfo_user_url)
        // } else {
        //     LOGIN_CB_URL = cninfo_user_url;
        //     $('#loginWrapper').show();
        //     $('#login_iframe').attr('src', cninfo_user_url_https + '/login?locale=zh&service=https://uc.cninfo.com.cn' + encodeURIComponent('/api/callback?client_name=CasClient&url=' + window.location.origin + '/new/transition'));
        // }
    })
    //我的问题
    $('.my-question').click(function () {
        if (JC_USER.getLoginStatus()) {
            window.open(cninfo_user_url + '/my_wd')
        } else {
            LOGIN_CB_URL = cninfo_user_url + '/my_wd';
            $('#loginWrapper').show();
            $('#login_iframe').attr('src', cninfo_user_url_https + '/login?locale=zh&service='+cninfo_user_url + encodeURIComponent('/api/callback?client_name=CasClient&url=' + window.location.origin + '/new/transition'));
        }
    })
    $('.close-login-btn').click(function () {
        closeModal();
    })
    $('#loginWrapper').click(function () {
        closeModal();
    })
})

//浏览器限制，不能调用所里退出接口，需要调用巨潮网退出
function logout() {
  window.location.href = 'https://uc.cninfo.com.cn/api/logout';

}

var closeModalEvent = new CustomEvent("loginCloseModal");

function closeModal() {
    $('#loginWrapper').hide();
    document.dispatchEvent(closeModalEvent);
    if (LOGIN_CB_TYPE == 'feedback_open') {
        getCommonUserInfo(function () {
            if (JC_USER.getLoginStatus()) {
                Feed_Back.openDialog();
                LOGIN_CB_TYPE = '';
            }
        })
    }

}

// 带缓存控制的刷新
function smartReload() {
  const timestamp = Date.now();
  const url = new URL(window.location.href);
  
  // 添加时间戳参数避免缓存
  url.searchParams.set('_t', timestamp);
  
  // 保留锚点
  const hash = window.location.hash;
  
  // 使用 replace 避免产生历史记录
  window.location.replace(url.toString() + hash);
}

