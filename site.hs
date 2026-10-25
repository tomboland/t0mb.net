{-# LANGUAGE OverloadedStrings #-}

import qualified Cinema as C
import CinemaRendering
import Publishing
import qualified View as V
import Control.Monad (forM_, when)
import qualified Data.Map.Strict as M
import Data.Aeson (Value(..), eitherDecodeStrict')
import qualified Data.Aeson.Key as K
import qualified Data.Aeson.KeyMap as KM
import qualified Data.Text as T
import qualified Data.Text.Encoding as TE
import System.Process (readProcess)
import qualified Data.Set as S
import Hakyll
import Hakyll.Core.Dependencies (DependencyKind(..))
import System.Directory (doesDirectoryExist, listDirectory, removeFile)
import System.Environment (getArgs)
import System.FilePath ((</>), replaceExtension, takeExtension)

main :: IO ()
main = do
  args <- getArgs
  if "clean" `elem` args then hakyll (pure ()) else hakyll $ do
    cinema <- preprocess C.loadCinema
    exportPacket <- preprocess $ do
      output <- readProcess "python3" ["scripts/export-cinema.py", "--public-stdout"] ""
      either fail pure $ eitherDecodeStrict' $ TE.encodeUtf8 $ T.pack output
    let exportView = V.set [("title",V.val "Film data for recommendations"),("nav_data",V.val "true")] $ V.get "view" exportPacket
        exportFiles = case V.get "files" exportPacket of
          Object rows -> [(K.toString key,V.text value) | (key,value) <- KM.toList rows]
          _ -> error "Invalid public export packet"
    noteSources <- getMatches notesPattern
    let pages = C.pageViews cinema
        published = C.latestReviews cinema
        reviewSources = map (fromFilePath . V.str "source") published
        reviewPattern = fromList reviewSources .&&. hasNoVersion
        writing = notesPattern .||. reviewPattern
        reviewBySource = M.fromList [(V.str "source" r, r) | r <- published]
        reviewFor identifier = case M.lookup (toFilePath identifier) reviewBySource of
          Just review -> review
          Nothing -> error ("Missing review: " ++ show identifier)
    tags <- preprocess $ loadPostTags $ noteSources ++ reviewSources
    let expected = S.fromList $ ["films/about/index.html", "films/data/index.html", "tags/index.html"]
          ++ ["films/data/"++name | (name,_) <- exportFiles]
          ++ [V.routePath url | (url,_,_) <- pages]
          ++ map (V.routePath . C.reviewUrl cinema) published
          ++ [V.routePath $ postTagUrl label | (label,_) <- tagGroups tags]
          ++ map (flip replaceExtension "html" . toFilePath) noteSources
    preprocess $ mapM_ (prune expected) ["films", "directors", "tags", "posts"]
    match "css/*" $ route idRoute >> compile compressCssCompiler
    match "robots.txt" $ route idRoute >> compile copyFileCompiler
    match ("images/**" .||. "js/*" .||. imagePattern) $ route idRoute >> compile copyFileCompiler
    match "templates/**" $ compile templateBodyCompiler
    match "content/home.md" $ compile pandocCompiler

    -- Dynamic routes and tag membership are computed before compilation.
    -- Track source edits, additions and removals for incremental builds as well.
    let sources = "cinema/*.json" .||. "cinema/reviews/*.md" .||. "posts/*/index.md" .||. "scripts/export-cinema.py" .||. "scripts/cinema_export.py" .||. "scripts/cinema_query.py" .||. "scripts/collection_data.py" .||. "scripts/cinema_data.py"
    match sources $ version "data" $ compile getResourceString
    dependency <- makePatternDependency KindContent $ sources .&&. hasVersion "data"
    rulesExtraDependencies [dependency] $ do
      create ["films/data/index.html"] $ do
        route idRoute
        compile $ makeItem "" >>= renderCinema "data" exportView
      forM_ exportFiles $ \(name,body) -> create [fromFilePath $ "films/data/"++name] $ do
        route idRoute
        compile $ makeItem body
      forM_ pages $ \(url,tpl,view) -> create [fromFilePath $ V.routePath url] $ do
        route idRoute
        compile $ do
          pageView <- if tpl == "film" then embedReviews tags view else pure view
          makeItem "" >>= renderCinema tpl pageView
      match reviewPattern $ do
        route $ customRoute $ \identifier -> V.routePath $ C.reviewUrl cinema $ reviewFor identifier
        compile $ do
          identifier <- getUnderlying
          let review = reviewFor identifier
              view = V.set [("nav_writing",V.val "true"),("postTags",tagLinks tags identifier)] $ C.reviewView cinema review
              context = V.viewContext view <> siteFields
          body <- pandocCompiler >>= saveSnapshot bodySnapshot
          _ <- loadAndApplyTemplate "templates/cinema/review-feed.html" context body >>= saveSnapshot feedSnapshot
          loadAndApplyTemplate "templates/cinema/review.html" context body >>= wrapCinema view
      match notesPattern $ do
        route $ customRoute $ flip replaceExtension "html" . toFilePath
        compile $ pandocCompiler >>= saveSnapshot bodySnapshot >>= saveSnapshot feedSnapshot
          >>= page "templates/post.html" (postCtx tags <> siteCtx)
      publishingRules writing tags (V.viewContext $ C.featuredReviewView cinema)
    match "content/films-about.md" $ do
      route $ constRoute "films/about/index.html"
      compile $ do
        title <- getMetadataField' "content/films-about.md" "title"
        pandocCompiler >>= renderCinema "about" (V.obj [("title",V.val title),("nav_films",V.val "true")])
    match "software.md" $ do
      route $ setExtension "html"
      compile $ pandocCompiler >>= loadAndApplyTemplate "templates/default.html" siteCtx >>= relativizeUrls
    match "content/content-use.md" $ do
      route $ constRoute "content-use/index.html"
      compile $ pandocCompiler >>= loadAndApplyTemplate "templates/default.html" siteCtx >>= relativizeUrls

imagePattern :: Pattern
imagePattern = "posts/**.jpg" .||. "posts/**.jpeg" .||. "posts/**.png" .||. "posts/**.gif" .||. "posts/**.webp" .||. "posts/**.avif"

prune :: S.Set FilePath -> FilePath -> IO ()
prune expected relative = do
  let path="_site" </> relative
  exists <- doesDirectoryExist path
  when exists $ do
    names <- listDirectory path
    forM_ names $ \name -> do
      let child=relative </> name
      directory <- doesDirectoryExist ("_site" </> child)
      if directory then prune expected child else
        when ((takeExtension child==".html" || relative=="films/data") && not (S.member child expected)) $ removeFile ("_site" </> child)
