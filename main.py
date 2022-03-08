from bs4 import BeautifulSoup
from requests_ntlm import HttpNtlmAuth
import requests
import json
import mimetypes
import os
import re
from urllib.parse import urlparse

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# global constants/variables are prefixed with G_

G_CMS_BASE_URL='https://cms.giu-uni.de'
G_CMS_ALL_COURSES_PAGE='/apps/student/ViewAllCourseStn'
G_NTLM_AUTH = None
G_SYMS_INVALID_IN_FILENAME="<>:\"/\|?*"
G_VIDEO_EXTENSIONS=['.mpg','.mp4','.webm','.avi','.mkv','.ts']


def make_filename_compatible(filename):
    out = ""
    for c in filename:
        if c in G_SYMS_INVALID_IN_FILENAME:
            out+="--"
        else:
            out+=c
    return out

def get_config_file(fileLoc):
    if os.path.isfile(fileLoc):
        with open(fileLoc,'r') as f:
            config = json.load(f)
            return config 
    return None

def set_config_file(config,fileLoc):
    with open(fileLoc,'w') as f:
        json.dump(config,f)



def get_course_content(html_str):

    document = BeautifulSoup(html_str,'html.parser')


    weeks ={}
    wnum = len(document.find_all('h2',class_='text-big',string=re.compile("Week")))

    for weekNode in document.find_all(class_='weeksdata'):
        week=f"Week {wnum}"
        wnum-=1

        weeks[week]=[]
        contents = weeks[week]


        weekNodeLinks = [ n.get('href') for n in weekNode.find_all(class_='btn btn-primary contentbtn')]
        current_node = weekNode.find_all(class_='card-body')
        weekNodeContentLabels = [ n.div.text for n in current_node]

        assert(len(weekNodeContentLabels)==len(weekNodeLinks))

        for i in range(len(weekNodeContentLabels)):
            contents+=[{
                'label' : weekNodeContentLabels[i],
                'link' : G_CMS_BASE_URL + weekNodeLinks[i],
                }]


    return weeks


def get_url_course_page(courseId,seasonid):
    return '/apps/student/CourseViewStn.aspx?id='+courseId+'&sid='+seasonid

def get_course_and_season_infos(html_str):

    seasons = []

    document = BeautifulSoup(html_str,'html.parser')
    courseTables = document.find_all(class_='col-md-12 col-lg-12 col-sm-12')

    for ct in courseTables:

        season = {}
        seasonInfoNode = ct.find(class_='menu-header-title')


        if seasonInfoNode and seasonInfoNode.text[0:6]=='Season':

            s_split = seasonInfoNode.text.split()
            season['id'] = s_split[2]
            season['title'] = s_split[5] + ' ' + s_split[6]
            season['courses'] = []

        courseRows = ct.find_all('tr')[1:]

        for cr in courseRows:
            cols = cr.find_all('td')
            courseId = cols[-2].text
            courseName = cols[1].text
            season['courses']+= [{
                'title' : courseName,
                'link' : G_CMS_BASE_URL + get_url_course_page(courseId,season['id'])
                }]

        if season:
            seasons+=[season]

    return seasons


def construct_season_directory_tree(season):
    dirs = []

    rootDir='/'+season['title']

    for course in season['courses']:
        dirs+=[f"{rootDir}/{course['title']}/"]

    return dirs



def sync_all_content(season,config):

    dirs = construct_season_directory_tree(season)
    filteredExtensions = G_VIDEO_EXTENSIONS if config['allowVideos'] else []

    for i,c in enumerate(season['courses']):
        courseDir = config['rootDir']+dirs[i]
        os.makedirs(courseDir,exist_ok=True)
        sync_course(c,courseDir,filteredExtensions)

def sync_course(course,courseDir,filteredExtensions):

    print("_________________________")
    print(f"syncing course : {bcolors.OKBLUE}{course['title']}{bcolors.ENDC}")
    print("_________________________\n")

    try:
        coursePageReq = requests.get(course['link'],auth=G_NTLM_AUTH)
    except requests.exceptions.RequestException as e:
        print(f" {bcolors.FAIL}PAGE FETCHING ERROR {bcolors.ENDC}: {e}")
        return

    courseWeeks = get_course_content(coursePageReq.content)

    for week in courseWeeks:
        for content in courseWeeks[week]:
            print(f"found content [ {bcolors.OKBLUE} '{content['label']}' {bcolors.ENDC} ]")
            content_url_path = urlparse(content['link']).path
            content_ext = os.path.splitext(content_url_path)[1]

            if content_ext.lower() in filteredExtensions:
                print(f"{bcolors.WARNING} type {content_ext} is filtered, skipping {bcolors.ENDC}\n")
                continue

            filePath = f"{courseDir}{week}/{make_filename_compatible(content['label'])}{content_ext}"

            if os.path.isfile(filePath):
                print(f"{bcolors.WARNING}content already exists, skipping {bcolors.ENDC}\n")
                continue

            print(f"GET :{bcolors.OKCYAN}{content['link']}{bcolors.ENDC}")

            try:
                contentRawStream = requests.get(content['link'],auth=G_NTLM_AUTH)
            except requests.exceptions.RequestException as e:
                print('CONTENT FETCHING ERROR : ',e)
                return

            print(f"{bcolors.OKGREEN} [SUCCESS] {bcolors.ENDC} saving as :",filePath,"\n")
            os.makedirs(f"{courseDir}{week}",exist_ok=True)
            with open(filePath,'wb') as f:
                f.write(contentRawStream.content)






def prompt(config):

    ans=''

    if config:
        while (ans!='n' and ans!='y'):
            ans = input(f"{bcolors.OKCYAN}would you like to change your configuration?{bcolors.ENDC} y/n? : ").lower()
    else:
        print(f"{bcolors.WARNING}no config file found, creating a new one {bcolors.ENDC}")

    if config==None or ans=='y':
        config = {
                "ntlmCredentials" : {},
                "rootDir" : os.getcwd()
        }

        while True:
            ans = input(f"{bcolors.OKCYAN}would you like to download videos? {bcolors.ENDC} y/n? : ").lower()

            if ans=='y':
                config['allowVideos']=True
                break

            if ans=='n':
                config['allowVideos']=False
                break



        while True:
            ans = input(f"{bcolors.OKCYAN}enter your GIU AS username : {bcolors.ENDC}")

            if not ans:
                print(f"{bcolors.ERROR}username can't be empty{bcolors.ENDC}")
            else:
                config['ntlmCredentials']['username']=ans
                break

        while True:
            ans = input(f"{bcolors.OKCYAN}enter your GIU AS password :{bcolors.ENDC} ")

            if not ans:
                print(f"{bcolors.ERROR}password can't be empty{bcolors.ENDC}")
            else:
                config['ntlmCredentials']['pass']=ans
                break

        ans = input(f"{bcolors.OKCYAN}specify the directory where you want to save the courses{bcolors.ENDC} (default : {config['rootDir']} ) : ")

        if ans:
            config['rootDir']=ans

        set_config_file(config,'./config.json')


    return config



try:


    config = get_config_file('./config.json')
    config = prompt(config)

    G_NTLM_AUTH = HttpNtlmAuth(config['ntlmCredentials']['username'],config['ntlmCredentials']['pass']);


    print(f"{bcolors.OKCYAN}fetching and scraping the CMS...{bcolors.ENDC}")

    courses_page_req = requests.get(G_CMS_BASE_URL + G_CMS_ALL_COURSES_PAGE,auth=G_NTLM_AUTH)
    seasons = get_course_and_season_infos(courses_page_req.content)
    sync_all_content(seasons[0],config)

except requests.exceptions.RequestException as e:
    print(e)



